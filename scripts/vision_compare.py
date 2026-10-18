#!/usr/bin/env python3
"""Step 4 (offline): put Gemini's detections on the map and compare them with the tree inventory.

Writes backend/data/vision/candidates.geojson (every detected tree, accepted or
for review), ground.geojson (shade/sun patches at photo time, for checking our
model) and report.json. Open the .geojson files on geojson.io to eyeball them.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.vision.compare import (aerial_candidates, candidate_feature, ground_features, match_inventory,  # noqa: E402
                                merge_duplicates, street_candidates)
from app.vision.geo import polygon_area_m2  # noqa: E402
from shapely.geometry import shape  # noqa: E402

VISION = ROOT / "backend/data/vision"
TREES = ROOT / "backend/data/ucla_trees.geojson"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-confidence", type=float, default=0.6,
                        help="Gemini confidence a new tree needs before it's accepted into the shade model")
    parser.add_argument("--trees", type=Path, default=TREES)
    args = parser.parse_args()

    if not (VISION / "photos.json").exists():
        raise SystemExit("No photos.json yet: run scripts/vision_fetch_images.py first.")
    photos = {p["id"]: p for p in json.loads((VISION / "photos.json").read_text(encoding="utf-8"))}
    inventory = json.loads(args.trees.read_text(encoding="utf-8"))["features"]
    candidates, ground, per_site = [], [], {}
    for path in sorted((VISION / "detections").glob("*.json")):
        detections = json.loads(path.read_text(encoding="utf-8"))
        photo = photos.get(detections["photo_id"])
        if photo is None:
            continue
        found = aerial_candidates(detections, photo) if photo["kind"] == "aerial" else street_candidates(detections, photo)
        candidates += found
        site = per_site.setdefault(photo["site_name"], {"photos": 0, "detections": 0, "ground_shade_m2": 0.0, "ground_sun_m2": 0.0})
        site["photos"] += 1
        site["detections"] += len(found)
        if photo["kind"] == "aerial":
            patches = ground_features(detections, photo)
            ground += patches
            for patch in patches:
                area = polygon_area_m2(list(shape(patch["geometry"]).exterior.coords)[:-1])
                site["ground_shade_m2" if patch["properties"]["state"] == "shade" else "ground_sun_m2"] += area

    merged = merge_duplicates(candidates)
    match_inventory(merged, inventory)
    features = [candidate_feature(c, args.min_confidence) for c in merged]
    accepted = sum(f["properties"]["status"] == "tree" for f in features)
    matched = [c for c in merged if c.matched_inventory]
    height_gaps = [abs(c.height_m - c.inventory_height_m) for c in matched if c.height_m and c.inventory_height_m]

    attribution = sorted({photos[s]["attribution"] for c in merged for s in c.sources})
    (VISION / "candidates.geojson").write_text(json.dumps({"type": "FeatureCollection", "metadata": {
        "method": "Gemini vision estimates; unverified", "attribution": attribution,
        "min_confidence": args.min_confidence}, "features": features}, indent=2), encoding="utf-8")
    (VISION / "ground.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": ground}, indent=2), encoding="utf-8")
    report = {
        "detections": len(candidates), "distinct_trees": len(merged), "accepted_new_trees": accepted,
        "already_in_inventory": len(matched), "needs_review": len(merged) - accepted - len(matched),
        # how far gemini's height guesses are from measured heights, on trees
        # both know: the best single number for "can we trust its new trees"
        "height_error_vs_inventory_m": {"count": len(height_gaps),
                                        "median": sorted(height_gaps)[len(height_gaps) // 2] if height_gaps else None},
        "sites": per_site,
    }
    (VISION / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
