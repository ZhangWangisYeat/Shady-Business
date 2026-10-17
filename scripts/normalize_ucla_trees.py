#!/usr/bin/env python3
"""Convert a permissioned UCLA tree-inventory CSV to normalized GeoJSON.

No network access; no automatically inferred tree geometry. The source must provide
WGS84 latitude/longitude, measured heights, and crown spread in chosen units.
Run --help for explicit column mapping. Output is locally generated and may not
be redistributed unless the source license/permission allows it.
"""

import argparse
import csv
import json
import math
from pathlib import Path

FEET_TO_METERS = 0.3048


def positive_measure(value: str | None, factor: float) -> float | None:
    if value is None or not str(value).strip():
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("measurement must be finite and greater than zero")
    return round(number * factor, 3)


def normalize_csv(input_path: Path, *, lat_col: str, lon_col: str,
                  height_col: str, crown_col: str,
                  unit: str, source: str) -> tuple[dict, dict]:
    factor = FEET_TO_METERS if unit == "ft" else 1.0
    features: list[dict] = []
    rejected = 0
    missing_height = 0
    missing_crown = 0
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {lat_col, lon_col, height_col, crown_col}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"CSV columns absent: {sorted(required - set(reader.fieldnames or []))}")
        for index, row in enumerate(reader, start=2):
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                height = positive_measure(row[height_col], factor)
                diameter = positive_measure(row[crown_col], factor)
                if not all(map(math.isfinite, [lat, lon])) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("invalid WGS84 coordinate")
            except (ValueError, TypeError):
                rejected += 1
                continue
            if height is None:
                missing_height += 1
            if diameter is None:
                missing_crown += 1
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "source": source, "source_csv_row": index,
                    "height_m": height,
                    "crown_radius_m": round(diameter / 2, 3) if diameter else None,
                    "height_method": "measured_inventory" if height else "unknown",
                    "shade_model_ready": bool(height and diameter),
                },
            })
    if not features:
        raise ValueError("No valid WGS84 tree records; confirm columns, units, and CRS")
    report = {"features": len(features), "rejected_rows": rejected,
              "missing_height": missing_height, "missing_crown": missing_crown,
              "shade_model_ready": sum(f["properties"]["shade_model_ready"] for f in features)}
    return {"type": "FeatureCollection", "features": features}, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--lat-column", required=True)
    parser.add_argument("--lon-column", required=True)
    parser.add_argument("--height-column", required=True)
    parser.add_argument("--crown-column", required=True, help="Crown SPREAD/DIAMETER, not radius")
    parser.add_argument("--units", choices=["ft", "m"], default="ft")
    parser.add_argument("--source", default="UCLA tree inventory, export with permission")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    geojson, report = normalize_csv(args.csv, lat_col=args.lat_column,
                                    lon_col=args.lon_column,
                                    height_col=args.height_column,
                                    crown_col=args.crown_column,
                                    unit=args.units, source=args.source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(geojson, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"output": str(args.out), **report}, indent=2))


if __name__ == "__main__":
    main()
