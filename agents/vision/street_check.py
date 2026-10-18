#!/usr/bin/env python3
"""Ground-level check of VisionLab's aerial results with Mapillary street photos.

For each tile VisionLab filled, it fetches a few street photos taken there,
measures how green each view is (green view index) and how much of the ground
is shaded, and compares that with the canopy VisionLab mapped from above. If
the aerial maps are right, greener-from-above tiles should look greener from
the street too.

    agents\\.venv\\Scripts\\python agents/vision/street_check.py --per-tile 4
"""
import argparse
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import shape

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "backend"))
from visionlab.analyze import land_cover  # noqa: E402
from visionlab.street import analyze_photo, photos_near  # noqa: E402

REPORTS = HERE / "data" / "reports"
PHOTOS = HERE / "data" / "street"


def token() -> str:
    from app.vision.keys import load_keys
    load_keys()
    value = os.environ.get("MAPILLARY_TOKEN")
    if not value:
        raise SystemExit("Set MAPILLARY_TOKEN (mobile/.env works)")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-tile", type=int, default=4)
    parser.add_argument("--radius", type=float, default=90)
    parser.add_argument("--trees", type=Path, default=REPO / "backend" / "data" / "ucla_trees_visionlab.geojson")
    args = parser.parse_args()

    key = token()
    coverage = shape(json.loads(args.trees.read_text(encoding="utf-8"))["metadata"]["coverage_geometry"])
    original = shape(json.loads((REPO / "backend" / "data" / "ucla_trees.geojson").read_text(encoding="utf-8"))["metadata"]["coverage_geometry"])
    # the tiles VisionLab added are what the new coverage has beyond the old
    added = coverage.difference(original)
    parts = list(getattr(added, "geoms", [added]))
    centers = []
    for part in parts:
        west, south, east, north = part.bounds
        lat_step, lon_step = 160 / 111_320, 160 / (111_320 * np.cos(np.radians((south + north) / 2)))
        for lat in np.arange(south + lat_step / 2, north, lat_step):
            for lon in np.arange(west + lon_step / 2, east, lon_step):
                if part.buffer(1e-5).contains(shape({"type": "Point", "coordinates": [lon, lat]})):
                    centers.append((lon, lat))
    print(f"{len(centers)} VisionLab-filled tiles to check from street level.")

    PHOTOS.mkdir(parents=True, exist_ok=True)
    rows = []
    for lon, lat in centers:
        try:
            images = photos_near(lon, lat, args.radius, key, args.per_tile)
        except Exception as exc:
            print(f"  Mapillary failed at {lat:.5f},{lon:.5f}: {exc}")
            continue
        if not images:
            continue
        aerial = land_cover(lon, lat, 160)
        canopy_from_above = aerial["shares"]["tree_canopy"] + aerial["shares"]["other_vegetation"]
        scores = []
        for image in images:
            path = PHOTOS / f"{image['id']}.jpg"
            if not path.exists():
                with urllib.request.urlopen(urllib.request.Request(image["thumb_1024_url"], headers={"User-Agent": "visionlab/0.1"}), timeout=30) as r:
                    path.write_bytes(r.read())
            scores.append({"id": image["id"], **analyze_photo(np.asarray(Image.open(path).convert("RGB")))})
        gvi = float(np.mean([s["green_view_index"] for s in scores]))
        rows.append({"center": [round(lon, 6), round(lat, 6)], "photos": len(scores), "aerial_vegetation_share": round(canopy_from_above, 3),
                     "aerial_tree_canopy_share": aerial["shares"]["tree_canopy"], "street_green_view_index": round(gvi, 3),
                     "street_ground_shade": round(float(np.nanmean([s["ground_shade_share"] or np.nan for s in scores])), 3),
                     "photo_scores": scores})
        print(f"  {lat:.5f},{lon:.5f}: {len(scores)} photos, green view {gvi:.0%} | from above: vegetation {canopy_from_above:.0%}")

    photos = sum(r["photos"] for r in rows)
    corr = (float(np.corrcoef([r["aerial_vegetation_share"] for r in rows], [r["street_green_view_index"] for r in rows])[0, 1])
            if len(rows) >= 3 else None)
    report = {"tiles_with_photos": len(rows), "photos": photos, "correlation_aerial_vs_street": None if corr is None else round(corr, 2),
              "credit": "Street-level imagery © Mapillary contributors, CC BY-SA 4.0", "tiles": rows}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "street_check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{photos} street photos over {len(rows)} tiles; correlation between vegetation seen from above and from the street: "
          f"{report['correlation_aerial_vs_street']}")

    # a contact sheet: each photo with its vegetation pixels tinted, for the demo
    sheet_photos = [s["id"] for r in rows for s in r["photo_scores"]][:8]
    if sheet_photos:
        thumbs = []
        for photo_id in sheet_photos:
            im = Image.open(PHOTOS / f"{photo_id}.jpg").convert("RGB").resize((384, 288))
            a = np.asarray(im).astype(np.float32)
            green = (2 * a[..., 1] - a[..., 0] - a[..., 2] > 20) & (a[..., 1] > 40)
            tinted = a.copy()
            tinted[green] = tinted[green] * 0.4 + np.array([40, 255, 90]) * 0.6
            im = Image.fromarray(tinted.astype(np.uint8))
            ImageDraw.Draw(im).rectangle([0, 0, 384, 22], fill=(0, 0, 0))
            ImageDraw.Draw(im).text((6, 5), f"green view {green.mean():.0%}  ·  Mapillary {photo_id}", fill=(255, 255, 255))
            thumbs.append(im)
        cols = 2
        sheet = Image.new("RGB", (384 * cols, 288 * ((len(thumbs) + 1) // cols)), "white")
        for i, im in enumerate(thumbs):
            sheet.paste(im, ((i % cols) * 384, (i // cols) * 288))
        out = HERE / "data" / "proof" / "4_street_check_contact_sheet.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out)
        print(f"Contact sheet: {out}")


if __name__ == "__main__":
    main()
