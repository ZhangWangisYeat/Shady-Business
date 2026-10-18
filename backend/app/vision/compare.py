"""Put Gemini's detections on the map and check them against the tree inventory."""
import hashlib
from dataclasses import dataclass, field
from math import pi, sqrt

from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union

from app.vision.geo import (bearing_of, centroid, grid_to_lonlat, horizontal_fov, meters_between, offset,
                            polygon_area_m2)

# the tree loader rejects crowns wider than this, and a "crown" that big is
# really several trees gemini couldn't split, so it waits for a person
MAX_SINGLE_CROWN_RADIUS_M = 12.0
# two detections this close (from different photos, say) are the same tree
SAME_TREE_M = 4.0


@dataclass
class Candidate:
    lon: float
    lat: float
    kind: str
    height_m: float | None
    crown_radius_m: float | None
    confidence: float
    # how far off the position could be. an aerial outline is placed to within
    # a couple of meters, a street-level guess at distance much less precisely.
    uncertainty_m: float
    sources: list[str] = field(default_factory=list)
    outline: list[tuple[float, float]] | None = None
    matched_inventory: str | None = None
    inventory_height_m: float | None = None

    @property
    def model_ready(self) -> bool:
        return (self.kind == "tree" and self.height_m is not None and self.crown_radius_m is not None
                and 0 < self.crown_radius_m <= MAX_SINGLE_CROWN_RADIUS_M)


def aerial_candidates(detections: dict, photo: dict) -> list[Candidate]:
    bbox = tuple(photo["bbox"])
    found = []
    for tree in detections["trees"]:
        outline = [grid_to_lonlat(x, y, bbox, photo.get("grid_crs", "EPSG:3857")) for x, y in tree["outline"]]
        area = polygon_area_m2(outline)
        if area <= 0:
            continue
        lon, lat = centroid(outline)
        found.append(Candidate(lon, lat, tree["kind"], tree["height_m"], sqrt(area / pi), tree["confidence"],
                               uncertainty_m=2.5, sources=[photo["id"]], outline=outline))
    return found


def street_candidates(detections: dict, photo: dict) -> list[Candidate]:
    lon, lat = photo["coordinate"]
    fov = horizontal_fov(photo.get("focal"))
    found = []
    for tree in detections["trees"]:
        column = tree["trunk_x"] if tree["trunk_x"] is not None else (tree["box"][0] + tree["box"][2]) / 2
        bearing = bearing_of(column, photo.get("heading") or 0, fov, bool(photo.get("panorama")))
        where = offset(lon, lat, bearing, tree["distance_m"])
        radius = tree["crown_width_m"] / 2 if tree["crown_width_m"] else None
        # distance from a single photo is a guess, so the error grows with it
        found.append(Candidate(where[0], where[1], tree["kind"], tree["height_m"], radius, tree["confidence"],
                               uncertainty_m=max(3.0, 0.25 * tree["distance_m"]), sources=[photo["id"]]))
    return found


def merge_duplicates(candidates: list[Candidate]) -> list[Candidate]:
    """One tree seen in several photos becomes one candidate.

    the most precisely placed sighting wins its position (aerial over street),
    and the sources are pooled so the report says which photos saw it.
    """
    merged: list[Candidate] = []
    for cand in sorted(candidates, key=lambda c: (c.uncertainty_m, -c.confidence)):
        twin = next((m for m in merged if meters_between((m.lon, m.lat), (cand.lon, cand.lat))
                     <= max(SAME_TREE_M, min(m.uncertainty_m, cand.uncertainty_m))), None)
        if twin is None:
            merged.append(cand)
            continue
        twin.sources = sorted(set(twin.sources + cand.sources))
        twin.confidence = max(twin.confidence, cand.confidence)
        if twin.height_m is None:
            twin.height_m = cand.height_m
        if twin.crown_radius_m is None:
            twin.crown_radius_m = cand.crown_radius_m
    return merged


def match_inventory(candidates: list[Candidate], inventory: list[dict]) -> None:
    """Mark candidates that are a tree we already have, so only new ones get added."""
    for cand in candidates:
        best, best_d = None, None
        for tree in inventory:
            lon, lat = tree["geometry"]["coordinates"]
            d = meters_between((cand.lon, cand.lat), (lon, lat))
            reach = max(SAME_TREE_M, cand.uncertainty_m, 0.75 * (tree["properties"].get("crown_radius_m") or 0))
            if d <= reach and (best_d is None or d < best_d):
                best, best_d = tree, d
        if best is not None:
            cand.matched_inventory = str(best["properties"].get("tree_id") or best["properties"].get("globalid"))
            cand.inventory_height_m = best["properties"].get("height_m")


def candidate_feature(cand: Candidate, min_confidence: float) -> dict:
    key = hashlib.sha1(f"{cand.lon:.6f},{cand.lat:.6f},{','.join(cand.sources)}".encode()).hexdigest()[:12]
    accepted = cand.model_ready and cand.confidence >= min_confidence and cand.matched_inventory is None
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [cand.lon, cand.lat]}, "properties": {
        "globalid": f"vision-{key}", "tree_id": f"vision-{key}",
        # only accepted candidates are "tree": the loader skips anything else,
        # so a shrub or an unsplit cluster can sit in the file for review
        # without casting a made-up shadow
        "status": "tree" if accepted else "vision_review",
        "kind": cand.kind, "height_m": cand.height_m, "crown_radius_m": cand.crown_radius_m,
        "height_method": "gemini_vision_estimate", "crown_method": "gemini_vision_estimate",
        "crown_base_m": None, "confidence": round(cand.confidence, 3), "uncertainty_m": round(cand.uncertainty_m, 1),
        "matched_inventory_tree": cand.matched_inventory, "inventory_height_m": cand.inventory_height_m,
        "sources": cand.sources, "shade_model_ready": accepted,
        "crown_outline": [[round(lon, 7), round(lat, 7)] for lon, lat in cand.outline] if cand.outline else None,
    }}


def ground_features(detections: dict, photo: dict) -> list[dict]:
    """Gemini's shade/sun ground patches for an aerial photo, for checking our model against.

    these are shade at the moment the photo was taken, so they never feed the
    route directly; the trees do, and the model casts their shadow for any time.
    """
    bbox = tuple(photo["bbox"])
    features = []
    for patch in detections["ground"]:
        ring = [grid_to_lonlat(x, y, bbox, photo.get("grid_crs", "EPSG:3857")) for x, y in patch["outline"]]
        polygon = Polygon(ring)
        if polygon.is_valid and polygon.area > 0:
            features.append({"type": "Feature", "geometry": mapping(polygon),
                             "properties": {"state": patch["state"], "source": photo["id"], "captured_at": photo.get("captured_at")}})
    return features


def footprint(photo: dict):
    west, south, east, north = photo["bbox"]
    return Polygon([(west, south), (east, south), (east, north), (west, north)])


def merged_tree_file(inventory_file: dict, candidates_file: dict, aerial_photos: list[dict],
                     extend_coverage: bool) -> dict:
    """The inventory plus accepted vision trees, as a new tree file the shade model can load.

    inventory trees always win: vision only adds trees the inventory doesn't
    have. coverage only grows (and only to analyzed aerial footprints) when
    asked, because saying "we know every tree here" is a claim a person makes,
    not the model.
    """
    metadata = dict(inventory_file.get("metadata") or {})
    accepted = [f for f in candidates_file["features"] if f["properties"].get("status") == "tree"]
    if extend_coverage and aerial_photos:
        old = shape(metadata["coverage_geometry"]) if metadata.get("coverage_geometry") else None
        grown = unary_union([g for g in [old, *(footprint(p) for p in aerial_photos)] if g is not None])
        metadata["coverage_geometry"] = mapping(grown)
    metadata["vision_supplement"] = {
        "added_trees": len(accepted), "method": "Gemini vision estimates from Mapillary (CC BY-SA 4.0) and "
        "USDA NAIP (public domain, via Microsoft Planetary Computer) photos", "independently_verified": False, "coverage_extended": bool(extend_coverage),
        "aerial_footprints": len(aerial_photos), "attribution": "Street-level imagery © Mapillary contributors, CC BY-SA 4.0",
    }
    metadata["quality"] = (metadata.get("quality", "") + "; plus unverified vision-estimated trees").lstrip("; ")
    return {"type": "FeatureCollection", "metadata": metadata,
            "features": list(inventory_file["features"]) + accepted}
