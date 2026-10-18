#!/usr/bin/env python3
"""Fill the shade dataset's gaps with VisionLab detections, as new tree and building files for the router.

For each walk, the stretches outside the inventory's coverage get aerial tiles
(with a margin, so the router has room to find other paths), or with
--everywhere every tile of the walking network outside it. On each tile
VisionLab finds tree crowns (height from crown width) and roofs (height from
roof size), both learned from UCLA's measured data. With --inventory, each
detected crown is checked against a wider tree inventory first: trees the
inventory has keep their measured height and spread, and only the crowns it
doesn't have are added as estimates. Nothing inside the existing coverage is
touched, so measured data always wins. The originals are
never modified; point the backend at the new files with SHADY_TREE_FILE and
SHADY_SHADE_FILE.

    agents\\.venv\\Scripts\\python agents/vision/fill_gaps.py --route olympic-hall royce-hall --route bruin-plate royce-hall
    agents\\.venv\\Scripts\\python agents/vision/fill_gaps.py --everywhere --inventory backend/data/ucla_trees_campus.geojson
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from visionlab.allometry import HeightModel  # noqa: E402
from visionlab.imagery import fetch_tile  # noqa: E402
from visionlab.models import MODELS, PixelModel  # noqa: E402
from visionlab.vectorize import clean, crowns, polygons  # noqa: E402

DATA = REPO / "backend" / "data"
ROUTER = "http://127.0.0.1:8000/api/routes"


def load_height(name: str) -> HeightModel:
    saved = json.loads((MODELS / name).read_text(encoding="utf-8"))
    return HeightModel(saved["slope"], saved["intercept"], saved["mae_m"], saved["within_25pct"], saved["trees"])


def route_lines(pairs: list[list[str]]) -> list[list[tuple[float, float]]]:
    lines = []
    for origin, destination in pairs:
        body = json.dumps({"origin": {"place_id": origin}, "destination": {"place_id": destination},
                           "departure_time": "2026-10-18T13:00:00-07:00", "temperature_c": 30}).encode()
        with urllib.request.urlopen(urllib.request.Request(ROUTER, body, {"Content-Type": "application/json"}), timeout=90) as r:
            for route in json.load(r)["routes"]:
                lines.append([tuple(c) for c in route["geometry"]["coordinates"]])
    return lines


def tiles_over(lines, coverage, size_m: float, margin_m: float):
    """A grid of square tiles over every uncovered stretch of the walks, plus a margin around them."""
    uncovered = [Point(p) for line in lines for p in line if not coverage.contains(Point(p))]
    if not uncovered:
        return []
    lat0 = np.mean([p.y for p in uncovered])
    step_lon, step_lat = size_m / (111_320 * np.cos(np.radians(lat0))), size_m / 111_320
    pad_lon, pad_lat = margin_m / (111_320 * np.cos(np.radians(lat0))), margin_m / 111_320
    west, south, east, north = unary_union(uncovered).bounds
    tiles = []
    for lon in np.arange(west - pad_lon, east + pad_lon, step_lon):
        for lat in np.arange(south - pad_lat, north + pad_lat, step_lat):
            cell = box(lon, lat, lon + step_lon, lat + step_lat)
            near = any(cell.buffer(max(pad_lon, pad_lat)).contains(p) for p in uncovered)
            if near and not coverage.contains(cell):
                tiles.append(cell.bounds)
    return tiles


def network_tiles(graph: Path, coverage, size_m: float):
    """A grid of square tiles over the whole walking network, minus what the coverage already has."""
    root = ET.parse(graph).getroot()
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    keys = {k.get("attr.name"): k.get("id") for k in root.findall("g:key", ns) if k.get("for") == "node"}
    nodes = []
    for node in root.iter("{http://graphml.graphdrawing.org/xmlns}node"):
        values = {d.get("key"): d.text for d in node.findall("g:data", ns)}
        nodes.append((float(values[keys["x"]]), float(values[keys["y"]])))
    nodes = np.array(nodes)
    lat0 = nodes[:, 1].mean()
    step_lon, step_lat = size_m / (111_320 * np.cos(np.radians(lat0))), size_m / 111_320
    west, south = nodes.min(0) - (step_lon, step_lat)
    east, north = nodes.max(0) + (step_lon, step_lat)
    tiles = []
    for lon in np.arange(west, east, step_lon):
        for lat in np.arange(south, north, step_lat):
            # a tile is needed when a walkway node sits in it or within half a
            # tile of it, so the edges between nodes in two tiles are covered too
            near = ((nodes[:, 0] > lon - step_lon / 2) & (nodes[:, 0] < lon + 1.5 * step_lon)
                    & (nodes[:, 1] > lat - step_lat / 2) & (nodes[:, 1] < lat + 1.5 * step_lat))
            cell = box(lon, lat, lon + step_lon, lat + step_lat)
            if near.any() and not coverage.contains(cell):
                tiles.append(cell.bounds)
    return tiles


def ident(prefix: str, lon: float, lat: float) -> str:
    return f"{prefix}-{hashlib.sha1(f'{lon:.7f},{lat:.7f}'.encode()).hexdigest()[:12]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--route", nargs=2, action="append", default=[], metavar=("ORIGIN_ID", "DESTINATION_ID"))
    parser.add_argument("--everywhere", action="store_true", help="fill every tile of the walking network outside the coverage")
    parser.add_argument("--graph", type=Path, default=DATA / "ucla_walk.graphml")
    parser.add_argument("--inventory", type=Path, help="a wider tree inventory to check detections against before adding them")
    parser.add_argument("--tile-size", type=float, default=160)
    parser.add_argument("--margin", type=float, default=120)
    parser.add_argument("--trees", type=Path, default=DATA / "ucla_trees.geojson")
    parser.add_argument("--buildings", type=Path, default=DATA / "ucla_buildings.geojson")
    parser.add_argument("--out-trees", type=Path, default=DATA / "ucla_trees_visionlab.geojson")
    parser.add_argument("--out-buildings", type=Path, default=DATA / "ucla_buildings_visionlab.geojson")
    args = parser.parse_args()
    for out, source in ((args.out_trees, args.trees), (args.out_buildings, args.buildings)):
        if out.resolve() == source.resolve():
            raise SystemExit("Refusing to overwrite a source file")

    trees_raw = json.loads(args.trees.read_text(encoding="utf-8"))
    buildings_raw = json.loads(args.buildings.read_text(encoding="utf-8"))
    coverage = shape(trees_raw["metadata"]["coverage_geometry"]).intersection(shape(buildings_raw["metadata"]["coverage_geometry"]))
    if not args.route and not args.everywhere:
        raise SystemExit("Give --route ORIGIN DESTINATION (any number) or --everywhere")
    if args.everywhere:
        tiles = network_tiles(args.graph, coverage, args.tile_size)
        print(f"{len(tiles)} aerial tiles cover the walking network outside the existing coverage.")
    else:
        lines = route_lines(args.route)
        tiles = tiles_over(lines, coverage, args.tile_size, args.margin)
        print(f"{len(lines)} routes; {len(tiles)} aerial tiles cover their uncovered stretches (+{args.margin:.0f} m).")
    known_ids = {f["properties"].get("globalid") for f in trees_raw["features"]}
    inventory = []
    if args.inventory:
        inventory = [f for f in json.loads(args.inventory.read_text(encoding="utf-8"))["features"]
                     if f["properties"].get("shade_model_ready") and f["properties"].get("globalid") not in known_ids]
    inv_xy = np.array([f["geometry"]["coordinates"] for f in inventory]) if inventory else np.zeros((0, 2))
    inv_r = np.array([f["properties"]["crown_radius_m"] for f in inventory]) if inventory else np.zeros(0)
    used_inventory = np.zeros(len(inventory), bool)
    matched_crowns = 0

    canopy_model, building_model = PixelModel.load("tree_canopy"), PixelModel.load("building")
    tree_height, building_height = load_height("tree_height.json"), load_height("building_height.json")
    new_trees, new_buildings, footprints = [], [], []
    started = time.time()
    for i, bounds in enumerate(tiles, 1):
        tile = fetch_tile(bounds)
        cell = box(*bounds)
        canopy = clean(canopy_model.predict(tile), tile)
        roofs = clean(building_model.predict(tile), tile, min_area_m2=20)
        west, south, east, north = bounds
        here = np.flatnonzero((inv_xy[:, 0] >= west) & (inv_xy[:, 0] < east) & (inv_xy[:, 1] >= south) & (inv_xy[:, 1] < north))
        for j in here:
            if not coverage.contains(Point(*inv_xy[j])):
                used_inventory[j] = True
        cos_lat = np.cos(np.radians((south + north) / 2))
        for crown in crowns(canopy & ~roofs, tile):
            radius = min(crown["crown_radius_m"], 12.0)  # an unsplit cluster is capped at a big single crown
            if coverage.contains(Point(crown["lon"], crown["lat"])):
                continue  # measured inventory already covers this ground
            if len(here):
                # a crown that lands on an inventory tree's canopy is that tree,
                # and the inventory's measured height beats an estimate
                dx = (inv_xy[here, 0] - crown["lon"]) * 111_320 * cos_lat
                dy = (inv_xy[here, 1] - crown["lat"]) * 111_320
                if (np.hypot(dx, dy) <= inv_r[here] + 3).any():
                    matched_crowns += 1
                    continue
            new_trees.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [crown["lon"], crown["lat"]]}, "properties": {
                "globalid": ident("visionlab-tree", crown["lon"], crown["lat"]), "tree_id": ident("visionlab-tree", crown["lon"], crown["lat"]),
                "status": "tree", "height_m": round(tree_height.predict(radius), 1), "crown_radius_m": round(radius, 2), "crown_base_m": None,
                "height_method": "visionlab_crown_allometry", "crown_method": "visionlab_naip_segmentation",
                "source": tile.source, "imagery_date": tile.captured, "shade_model_ready": True}})
        for poly in polygons(roofs, tile, simplify_m=0.8):
            if coverage.contains(poly.centroid) or not poly.is_valid or poly.is_empty:
                continue
            area = poly.area * 111_320 ** 2 * np.cos(np.radians(poly.centroid.y))
            new_buildings.append({"type": "Feature", "geometry": mapping(poly), "properties": {
                "id": ident("visionlab-building", poly.centroid.x, poly.centroid.y),
                "height_m": round(min(60.0, max(3.0, building_height.predict(np.sqrt(area / np.pi)))), 1),
                "height_method": "visionlab_roof_size_regression", "footprint_method": "visionlab_naip_segmentation",
                "source": tile.source, "imagery_date": tile.captured}})
        footprints.append(cell)
        if i % 10 == 0:
            print(f"  {i}/{len(tiles)} tiles, {len(new_trees)} trees and {len(new_buildings)} buildings so far ({time.time() - started:.0f} s)")

    from_inventory = []
    for j in np.flatnonzero(used_inventory):
        feature = json.loads(json.dumps(inventory[j]))
        feature["properties"]["coverage_vouched_by"] = "visionlab_tile_scan"
        from_inventory.append(feature)
    estimated = len(new_trees)
    print(f"Inventory check: {matched_crowns} detected crowns matched an inventory tree (kept its measurements), "
          f"{len(from_inventory)} inventory trees brought in, {estimated} crowns not in the inventory added as estimates.")
    new_trees = from_inventory + new_trees
    grown = unary_union([coverage, *footprints])
    evidence = {"type": "visionlab_estimate", "agent": "visionlab (Agentverse agent1qf0kxk6uevd2hq98lsxtdzn6wgv7dphk6p6jn22kmp5e3jh9u7yc78k2j9e)",
                "generated_at": datetime.now(timezone.utc).isoformat(), "tiles": len(footprints),
                "tree_height_mae_m": tree_height.mae_m, "building_height_mae_m": building_height.mae_m,
                "independently_verified": False, "routes": args.route or "whole walking network",
                "inventory_checked": args.inventory.name if args.inventory else None,
                "inventory_trees_added": len(from_inventory), "crowns_matched_to_inventory": matched_crowns,
                "estimated_trees_added": estimated, "canopy_model": canopy_model.trained_on}
    for raw, added, out, label in ((trees_raw, new_trees, args.out_trees, "trees"), (buildings_raw, new_buildings, args.out_buildings, "buildings")):
        metadata = dict(raw["metadata"])
        metadata["coverage_geometry"] = mapping(grown)
        metadata["visionlab_supplement"] = {**evidence, f"added_{label}": len(added)}
        extra = (f"{len(from_inventory)} measured inventory trees and {estimated} unverified VisionLab-estimated trees"
                 if label == "trees" else f"{len(added)} unverified VisionLab-estimated buildings")
        metadata["quality"] = (metadata.get("quality", "") + f"; plus {extra} in VisionLab-scanned tiles outside the original coverage").lstrip("; ")
        out.write_text(json.dumps({"type": "FeatureCollection", "metadata": metadata, "features": raw["features"] + added}), encoding="utf-8")
    print(f"Added {len(new_trees)} trees and {len(new_buildings)} buildings over {len(footprints)} tiles in {time.time() - started:.0f} s.")
    print(f"Wrote {args.out_trees.name} and {args.out_buildings.name}. Use them with:\n"
          f'  $env:SHADY_TREE_FILE="{args.out_trees}"; $env:SHADY_SHADE_FILE="{args.out_buildings}"')


if __name__ == "__main__":
    main()
