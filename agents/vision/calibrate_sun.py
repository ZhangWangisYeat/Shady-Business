#!/usr/bin/env python3
"""Find the sun in the NAIP photo from buildings of known height, then check shadow-measured heights against them.

    agents\\.venv\\Scripts\\python agents/vision/calibrate_sun.py --buildings backend/data/ucla_buildings.geojson
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from shapely.geometry import shape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from visionlab.heights import fit_sun, roof_heights  # noqa: E402
from visionlab.imagery import bbox_around, fetch_tile  # noqa: E402
from visionlab.labels import rasterize  # noqa: E402
from visionlab.models import MODELS, PixelModel, shadow, vegetation  # noqa: E402
from visionlab.vectorize import clean  # noqa: E402

REPORTS = HERE / "data" / "reports"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--buildings", type=Path, required=True)
    parser.add_argument("--tiles", type=int, default=6, help="how many 250 m tiles (those with the most known buildings)")
    args = parser.parse_args()

    raw = json.loads(args.buildings.read_text(encoding="utf-8"))
    known = [(shape(f["geometry"]), f["properties"]["height_m"]) for f in raw["features"] if f["properties"].get("height_m")]
    centers = np.array([[g.centroid.x, g.centroid.y] for g, _ in known])
    # tiles centered on the densest clusters of known buildings
    picked, used = [], np.zeros(len(known), bool)
    canopy_model = PixelModel.load("tree_canopy") if "tree_canopy" in PixelModel.available() else None
    building_model = PixelModel.load("building")
    for _ in range(args.tiles):
        counts = [((np.abs(centers - c) < [0.0012, 0.001]).all(1) & ~used).sum() for c in centers]
        best = int(np.argmax(counts))
        if counts[best] < 2:
            break
        near = (np.abs(centers - centers[best]) < [0.0012, 0.001]).all(1)
        used |= near
        picked.append((centers[best], [known[i] for i in np.flatnonzero(near)]))

    batches, captured = [], None
    for (lon, lat), members in picked:
        tile = fetch_tile(bbox_around(lon, lat, 250))
        captured = tile.captured
        canopy = clean(canopy_model.predict(tile), tile) if canopy_model else vegetation(tile)
        # the roof as the photo shows it (from the building model), not the
        # osm footprint: tall buildings lean in aerial photos, so a footprint
        # sits off the roof and its "shadow" would start in the wrong place
        seen = clean(building_model.predict(tile), tile, min_area_m2=20)
        regions, _ = ndimage.label(seen)
        matched = []
        for g, h in members:
            footprint = rasterize(tile, [g])
            ids, counts = np.unique(regions[footprint & seen], return_counts=True)
            if len(ids) and counts.max() >= 0.4 * footprint.sum():
                matched.append((regions == ids[np.argmax(counts)], h))
        dark = shadow(tile, exclude=canopy | seen)
        blocked = canopy | ~tile.valid
        batches.append((tile, matched, dark, blocked))
    sun = fit_sun(batches, captured, *picked[0][0])
    print(f"Sun in the {captured} NAIP photo: azimuth {sun.azimuth_deg:.0f} deg, elevation {sun.elevation_deg:.0f} deg "
          f"(around {sun.time_utc[11:16]} UTC), fit {sun.fit_score} over {sun.calibration_buildings} buildings.")

    # check: measure every known building's height from its shadow with that sun
    errors, measured = [], 0
    for tile, members, dark, blocked in batches:
        roofs = np.zeros(tile.shape, bool)
        for roof, _ in members:
            roofs |= roof
        for roof, height in members:
            [result] = roof_heights(tile, roof, dark, blocked | (roofs & ~roof), sun) or [None]
            if result and result["height_m"] is not None:
                measured += 1
                errors.append(abs(result["height_m"] - height))
    report = {"sun": sun.__dict__, "photo_date": captured, "buildings_checked": sum(len(m) for _, m, _, _ in batches),
              "heights_measured": measured,
              "height_mae_m": round(float(np.mean(errors)), 2) if errors else None,
              "height_median_error_m": round(float(np.median(errors)), 2) if errors else None,
              "within_3m": round(float(np.mean(np.array(errors) <= 3)), 3) if errors else None}
    MODELS.mkdir(parents=True, exist_ok=True)
    (MODELS / "sun.json").write_text(json.dumps(sun.__dict__, indent=2), encoding="utf-8")
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "building_heights_from_shadows.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
