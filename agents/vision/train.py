#!/usr/bin/env python3
"""Train a VisionLab target from any labeled GeoJSON, and report how well it does on tiles it never saw.

Labels can be polygons (building footprints, ponds, solar arrays) or points
with a radius property (a tree inventory: trunk + crown spread). Tiles are cut
over the labeled area, split into training and held-out sets, and the model is
scored on the held-out ones against the labels and against a built-in baseline.

    agents\\.venv\\Scripts\\python agents/vision/train.py --target tree_canopy --labels backend/data/ucla_trees.geojson --radius-property crown_radius_m --baseline vegetation --heights
    agents\\.venv\\Scripts\\python agents/vision/train.py --target building --labels backend/data/ucla_buildings.geojson
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from shapely.geometry import shape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from visionlab.allometry import HeightModel  # noqa: E402
from visionlab.compare import mask_scores  # noqa: E402
from visionlab.imagery import fetch_tile  # noqa: E402
from visionlab.labels import geometries, rasterize  # noqa: E402
from visionlab.models import EXPERTS, MODELS, PixelModel  # noqa: E402
from visionlab.vectorize import clean, crowns  # noqa: E402

REPORTS = HERE / "data" / "reports"


def labeled_area(raw: dict, shapes) -> tuple[float, float, float, float]:
    """Where the labels claim to be complete: the dataset's own coverage polygon, else the labels' extent."""
    coverage = (raw.get("metadata") or {}).get("coverage_geometry")
    if coverage:
        return shape(coverage).bounds
    bounds = np.array([g.bounds for g in shapes])
    return (*bounds[:, :2].min(0), *bounds[:, 2:].max(0))


def grid(bounds, size_m: float, shapes, min_objects: int):
    west, south, east, north = bounds
    step_lon = size_m / (111_320 * np.cos(np.radians((south + north) / 2)))
    step_lat = size_m / 111_320
    centers = np.array([[g.centroid.x, g.centroid.y] for g in shapes])
    tiles = []
    for lon in np.arange(west, east - step_lon / 2, step_lon):
        for lat in np.arange(south, north - step_lat / 2, step_lat):
            box = (lon, lat, lon + step_lon, lat + step_lat)
            inside = ((centers[:, 0] >= box[0]) & (centers[:, 0] < box[2]) & (centers[:, 1] >= box[1]) & (centers[:, 1] < box[3]))
            if inside.sum() >= min_objects:
                tiles.append((box, np.flatnonzero(inside)))
    return tiles


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="name for the new model, e.g. tree_canopy, building, solar_panel")
    parser.add_argument("--labels", type=Path, required=True, help="GeoJSON of examples (complete for the area they cover)")
    parser.add_argument("--radius-property", help="for point labels: the property holding each object's radius in meters")
    parser.add_argument("--baseline", choices=sorted(EXPERTS), help="built-in model to compare against")
    parser.add_argument("--heights", action="store_true", help="also fit height from crown radius (needs height_m on the labels)")
    parser.add_argument("--tile-size", type=float, default=160)
    parser.add_argument("--min-objects", type=int, default=0, help="skip tiles with fewer labeled objects (default: auto)")
    parser.add_argument("--test-share", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    raw = json.loads(args.labels.read_text(encoding="utf-8"))
    features = [f for f in raw["features"] if f.get("geometry")]
    shapes = geometries(features, args.radius_property)
    points = args.radius_property is not None
    minimum = args.min_objects or (15 if points else 2)
    tiles = grid(labeled_area(raw, shapes), args.tile_size, shapes, minimum)
    if len(tiles) < 4:
        raise SystemExit(f"Only {len(tiles)} tiles have labels; need at least 4 to train and test")
    order = np.random.default_rng(args.seed).permutation(len(tiles))
    n_test = max(2, round(len(tiles) * args.test_share))
    test_ids, train_ids = order[:n_test], order[n_test:]
    print(f"{args.target}: {len(shapes)} labeled objects, {len(tiles)} usable {args.tile_size:.0f} m tiles; "
          f"training on {len(train_ids)}, testing on {len(test_ids)} it never sees.")

    def prepare(i):
        box, members = tiles[i]
        tile = fetch_tile(box)
        mask = rasterize(tile, shapes)
        # labels are only roughly the right shape (a disc for a crown, a
        # footprint that doesn't lean like the photo does), so a thin band
        # around every edge is left out of training and scoring
        band_deg = 1.2 / 111_320
        fuzzy = rasterize(tile, [g.buffer(band_deg) for g in shapes]) & ~rasterize(tile, [g.buffer(-band_deg) for g in shapes if not g.buffer(-band_deg).is_empty])
        return tile, mask, fuzzy, members

    started = time.time()
    train = [prepare(i) for i in train_ids]
    test = [prepare(i) for i in test_ids]
    print(f"Fetched and labeled {len(train) + len(test)} tiles in {time.time() - started:.0f} s.")

    started = time.time()
    model = PixelModel(args.target).fit([t for t, _, _, _ in train], [m for _, m, _, _ in train], [f for _, _, f, _ in train])
    model.threshold = float(max(np.arange(0.3, 0.8, 0.05), key=lambda cut: np.mean([
        mask_scores(model.probability(t) >= cut, m, t.valid & ~f)["iou"] or 0 for t, m, f, _ in train])))
    print(f"Trained on {model.trained_on['pixels']:,} pixels in {time.time() - started:.0f} s (cut {model.threshold:.2f}).")

    def evaluate(predict):
        scores, hit, total = [], 0, 0
        for tile, mask, fuzzy, members in test:
            predicted = clean(predict(tile), tile)
            scores.append(mask_scores(predicted, mask, tile.valid & ~fuzzy))
            for i in members:
                g = shapes[i]
                total += 1
                if points:
                    # a point label counts as found if its center is under the detection
                    r, c = tile.lonlat_to_pixel(g.centroid.x, g.centroid.y)
                    hit += bool(0 <= r < predicted.shape[0] and 0 <= c < predicted.shape[1] and predicted[int(r), int(c)])
                else:
                    # a polygon counts as found if at least half of it is detected
                    own = rasterize(tile, [g]) & tile.valid
                    hit += bool(own.sum() and (predicted & own).sum() >= 0.5 * own.sum())
        mean = lambda k: round(float(np.mean([s[k] for s in scores if s[k] is not None])), 3)
        return {"pixel_iou": mean("iou"), "pixel_precision": mean("precision"), "pixel_recall": mean("recall"),
                "objects_found": round(hit / max(total, 1), 3), "objects": total}

    report = {"target": args.target, "labels": args.labels.name, "label_objects": len(shapes), "tile_size_m": args.tile_size,
              "train_tiles": len(train), "test_tiles": len(test), "threshold": model.threshold,
              "held_out": {"trained_model": evaluate(model.predict)}}
    if args.baseline:
        report["held_out"][f"{args.baseline}_baseline"] = evaluate(EXPERTS[args.baseline])
    if points:
        detected = sum(len(crowns(clean(model.predict(t), t), t)) for t, _, _, _ in test)
        report["held_out"]["trained_model"]["crowns_detected"] = detected
    if args.heights:
        heights = HeightModel.fit([f["properties"]["height_m"] for f in features if f["properties"].get("height_m") and f["properties"].get(args.radius_property)],
                                  [f["properties"][args.radius_property] for f in features if f["properties"].get("height_m") and f["properties"].get(args.radius_property)])
        report["height_from_crown"] = {"slope": heights.slope, "intercept": heights.intercept, "mae_m": round(heights.mae_m, 2),
                                       "within_25pct": round(heights.within_25pct, 3), "trees": heights.trained_on}
        (MODELS / "tree_height.json").parent.mkdir(parents=True, exist_ok=True)
        (MODELS / "tree_height.json").write_text(json.dumps(report["height_from_crown"], indent=2), encoding="utf-8")
    model.save()
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{args.target}_training.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["held_out"], indent=2))


if __name__ == "__main__":
    main()
