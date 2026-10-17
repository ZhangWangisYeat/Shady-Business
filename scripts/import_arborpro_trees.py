#!/usr/bin/env python3
"""Normalize the EXISTING local UCLA ArborPro CSV; no provider requests.

Explicit bbox is a study rectangle, not a verified campus property boundary.
Status 1 is Tree in this public inventory (cross-checked against viewer records).
Keep dimensionless/zero-dimension standing records as unknown; exclude stumps
and vacant sites. Generated geodata stays local and is not a redistribution grant.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

VIEWER = "https://app.arborprousa.com/viewer/7q07Ea8G2uVSf6KR/"
REQUIRED = {"globalid", "latitude", "longitude", "Tree ID", "Status", "Height (feet)", "Crown (feet)"}


def _measurement(value, maximum):
    try:
        number = float(value) * .3048
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and 0 < number <= maximum else None


def normalize_inventory(path: Path, bbox: tuple[float, float, float, float]) -> tuple[dict, dict]:
    west, south, east, north = bbox
    if not (-118.49 <= west < east <= -118.40 and 34.04 <= south < north <= 34.10):
        raise ValueError("Study bbox must be west south east north inside UCLA service bounds")
    report = dict(source_rows=0, outside_study_rectangle=0, invalid_coordinates=0,
                  non_tree_records=0, standing_tree_records=0, model_ready=0,
                  missing_height=0, missing_crown=0)
    features, seen = [], set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED.issubset(reader.fieldnames or ()):
            raise ValueError(f"Missing ArborPro columns: {sorted(REQUIRED - set(reader.fieldnames or ()))}")
        for row_number, row in enumerate(reader, start=2):
            report["source_rows"] += 1
            identity = (row.get("globalid") or "").strip()
            if not identity or identity in seen:
                raise ValueError("Tree CSV requires unique nonempty globalid values")
            seen.add(identity)
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
                if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("Invalid WGS84 point")
            except (ValueError, TypeError):
                report["invalid_coordinates"] += 1
                continue
            if not (west <= lon <= east and south <= lat <= north):
                report["outside_study_rectangle"] += 1
                continue
            if (row.get("Status") or "").strip().lower() not in ("1", "tree"):
                report["non_tree_records"] += 1
                continue
            height = _measurement(row["Height (feet)"], 100)
            diameter = _measurement(row["Crown (feet)"], 100)
            report["standing_tree_records"] += 1
            report["missing_height"] += height is None
            report["missing_crown"] += diameter is None
            report["model_ready"] += height is not None and diameter is not None
            features.append({"type": "Feature", "geometry": {
                "type": "Point", "coordinates": [lon, lat]}, "properties": {
                "globalid": identity, "tree_id": row["Tree ID"], "status": "tree",
                "source_status_code": row["Status"], "source_csv_row": row_number,
                "height_m": height, "crown_radius_m": diameter / 2 if diameter is not None else None,
                "height_method": "measured_inventory" if height is not None else "unknown",
                "crown_method": "inventory_spread_divided_by_two" if diameter is not None else "unknown",
                "crown_base_m": None, "botanical": row.get("Botanical") or None,
                "common": row.get("Common") or None,
                "shade_model_ready": height is not None and diameter is not None,
            }})
    if not features:
        raise ValueError("No standing-tree records inside the selected study rectangle")
    metadata = {
        "source": "UCLA ArborPro public tree inventory", "source_url": VIEWER,
        "source_file_checksum": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "imported_at": datetime.now(timezone.utc).isoformat(), "retrieved_at": None,
        "data_as_of": None, "source_inventory_period": "2023-2024; per-record observation date unavailable",
        "coordinate_reference_system": "EPSG:4326", "height_unit": "m", "crown_radius_unit": "m",
        "source_dimension_unit": "ft", "source_crown_semantics": "horizontal spread/diameter",
        "study_bbox": list(bbox), "scope": "Study rectangle, not a verified UCLA property boundary",
        "coverage_complete_verified": False,
        "license_or_permission": "Existing local dataset used at user's request; public redistribution rights unverified",
        "quality": "Inventory dimensions; vertical crown shape, opacity and current condition unverified",
        "import_report": report,
    }
    return {"type": "FeatureCollection", "metadata": metadata, "features": features}, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.csv.resolve() == args.out.resolve():
            raise ValueError("Output must not overwrite the source CSV")
        data, report = normalize_inventory(args.csv, tuple(args.bbox))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.out), **report}, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, f"Invalid inventory input: {error}\n")


if __name__ == "__main__":
    main()
