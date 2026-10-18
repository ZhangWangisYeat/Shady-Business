#!/usr/bin/env python3
"""Train VisionLab's tree-canopy model from a tree inventory, and report how well it does on unseen tiles.

The inventory is the teacher: each measured tree becomes a crown-shaped label
(a disc of its crown radius) on the NAIP aerial tile. Tiles are split into
training and held-out sets, so the reported accuracy is on ground the model
never saw. The same run fits the height-from-crown curve the shade model needs.

    agents\\.venv\\Scripts\\python agents/vision/train_canopy.py --inventory backend/data/ucla_trees.geojson
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from visionlab.allometry import HeightModel  # noqa: E402
from visionlab.compare import mask_scores, match_points  # noqa: E402
from visionlab.imagery import fetch_tile  # noqa: E402
from visionlab.labels import geometries, rasterize  # noqa: E402
from visionlab.models import PixelModel, vegetation  # noqa: E402
from visionlab.vectorize import clean, crowns  # noqa: E402

REPORTS = HERE / "data" / "reports"


def grid_tiles(trees: list[dict], bounds, size_m: float, min_trees: int):
    """Square tiles over the inventory's area, keeping ones with enough trees to learn from."""
    west, south, east, north = bounds
    step_lon = size_m / (111_320 * np.cos(np.radians((south + north) / 2)))
    step_lat = size_m / 111_320
    points = np.array([t["geometry"]["coordinates"][:2] for t in trees])
    tiles = []
    for lon in np.arange(west, east - step_lon / 2, step_lon):
        for lat in np.arange(south, north - step_lat / 2, step_lat):
            box = (lon, lat, lon + step_lon, lat + step_lat)
            inside = (points[:, 0] >= box[0]) & (points[:, 0] < box[2]) & (points[:, 1] >= box[1]) & (points[:, 1] < box[3])
            if inside.sum() >= min_trees:
                tiles.append((box, [trees[i] for i in np.flatnonzero(inside)]))
    return tiles


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inventory", type=Path, required=True, help="GeoJSON points with height_m and crown_radius_m")
    parser.add_argument("--tile-size", type=float, default=160)
    parser.add_argument("--min-trees", type=int, default=25)
    parser.add_argument("--train-tiles", type=int, default=12)
    parser.add_argument("--test-tiles", type=int, default=5)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    raw = json.loads(args.inventory.read_text(encoding="utf-8"))
    trees = [f for f in raw["features"] if (f.get("properties") or {}).get("crown_radius_m") and f["properties"].get("height_m")]
    coverage = (raw.get("metadata") or {}).get("coverage_geometry")
    xs = [t["geometry"]["coordinates"][0] for t in trees]
    ys = [t["geometry"]["coordinates"][1] for t in trees]
    bounds = (min(xs), min(ys), max(xs), max(ys)) if not coverage else tuple(np.array(coverage["coordinates"][0]).min(0)) + tuple(np.array(coverage["coordinates"][0]).max(0))
    candidates = grid_tiles(trees, bounds, args.tile_size, args.min_trees)
    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(candidates))
    train_idx, test_idx = order[: args.train_tiles], order[args.train_tiles: args.train_tiles + args.test_tiles]
    print(f"{len(trees)} measured trees, {len(candidates)} usable {args.tile_size:.0f} m tiles; "
          f"training on {len(train_idx)}, testing on {len(test_idx)} it never sees.")

    def labeled(i):
        box, inside = candidates[i]
        tile = fetch_tile(box)
        crowns_true = geometries(inside, radius_property="crown_radius_m")
        mask = rasterize(tile, crowns_true)
        # a disc is only roughly a crown's shape, so a band around each edge
        # is left out of training instead of being called "not tree"
        fuzzy = rasterize(tile, [g.buffer((g.bounds[3] - g.bounds[1]) * 0.15) for g in crowns_true]) & ~mask
        return tile, mask, fuzzy, inside

    started = time.time()
    train = [labeled(i) for i in train_idx]
    test = [labeled(i) for i in test_idx]
    print(f"Fetched {len(train) + len(test)} tiles in {time.time() - started:.0f} s.")

    started = time.time()
    model = PixelModel("tree_canopy").fit([t for t, _, _, _ in train], [m for _, m, _, _ in train], [f for _, _, f, _ in train])
    print(f"Trained on {model.trained_on['pixels']:,} pixels in {time.time() - started:.0f} s.")

    # pick the probability cut that best matches the inventory on the
    # training tiles, rather than assuming 0.5 is right
    best = max(np.arange(0.3, 0.8, 0.05), key=lambda cut: np.mean([
        mask_scores(model.probability(t) >= cut, m, t.valid & ~f)["iou"] or 0 for t, m, f, _ in train]))
    model.threshold = float(best)

    heights = HeightModel.fit([t["properties"]["height_m"] for t in trees], [t["properties"]["crown_radius_m"] for t in trees])

    def evaluate(predict):
        pixel, found = [], {"tp": 0, "detections": 0, "reference": 0, "under": 0}
        for tile, mask, fuzzy, inside in test:
            predicted = clean(predict(tile), tile)
            pixel.append(mask_scores(predicted, mask, tile.valid & ~fuzzy))
            detected = crowns(predicted, tile)
            result = match_points(detected, inside, reference_radius="crown_radius_m")
            found["tp"] += len(result["matches"])
            found["detections"] += len(detected)
            found["reference"] += len(inside)
            # for shade what matters is whether a tree is under detected
            # canopy at all, not whether it got a crown of its own: on campus
            # several trees often share one merged canopy
            for t in inside:
                r, c = tile.lonlat_to_pixel(*t["geometry"]["coordinates"][:2])
                if 0 <= r < predicted.shape[0] and 0 <= c < predicted.shape[1] and predicted[int(r), int(c)]:
                    found["under"] += 1
        avg = lambda k: float(np.mean([p[k] for p in pixel if p[k] is not None]))
        return {"pixel_iou": round(avg("iou"), 3), "pixel_precision": round(avg("precision"), 3), "pixel_recall": round(avg("recall"), 3),
                "trees_under_detected_canopy": round(found["under"] / found["reference"], 3),
                "trees_with_own_crown": round(found["tp"] / found["reference"], 3), "crowns_detected": found["detections"],
                "crowns_matching_a_tree": round(found["tp"] / max(found["detections"], 1), 3), "inventory_trees": found["reference"]}

    trained = evaluate(model.predict)
    baseline = evaluate(vegetation)
    path = model.save()
    report = {"target": "tree_canopy", "inventory": str(args.inventory.name), "tile_size_m": args.tile_size,
              "train_tiles": len(train), "test_tiles": len(test), "threshold": model.threshold,
              "held_out": {"trained_model": trained, "ndvi_baseline": baseline},
              "height_from_crown": {"slope": heights.slope, "intercept": heights.intercept, "mae_m": round(heights.mae_m, 2),
                                    "within_25pct": round(heights.within_25pct, 3), "trees": heights.trained_on},
              "note": "Truth is the inventory, which lists managed trees only, so precision is a lower bound."}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "tree_canopy_training.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (path.parent / "tree_height.json").write_text(json.dumps(report["height_from_crown"], indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
