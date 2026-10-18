#!/usr/bin/env python3
"""Apply user-provided approximate heights to the local UCLA shade input.

Unnamed roof/tent/shed features are excluded from shade obstruction modeling;
this does not add them to or otherwise modify the pedestrian routing graph.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re


HEIGHTS = {
    184444681: ("Engineering VI", 23.0),
    1026506167: ("Ostin Music Center A", 9.0),
    185081403: ("Entrepreneurs Hall", 21.3),
    184446757: ("Gold Hall", 21.3),
    30724960: ("Parking 5", 15.0),
    1026506158: ("Ostin Music Center B", 12.0),
    1423107802: ("Young Hall", 24.0),
    184488678: ("Cornell Hall", 21.3),
    407528998: ("Luskin Conference Center", 27.0),
    184488681: ("Mullin Management Commons", 18.3),
    185084330: ("Court of Sciences Student Center", 5.0),
    854806689: ("Rosenfeld Library", 18.3),
    792359253: ("Parking Information Kiosk", 3.0),
    422876588: ("La Kretz Hall", 13.0),
    590016847: ("Wasserman Football Center", 16.0),
    590011366: ("Mo Ostin Basketball Center", 13.0),
}
IGNORED = {1019348613, 964477264, 1560056342}
SOURCE = "User-provided approximate heights from referenced screenshots (2026-10-17)"


def _way_id(value) -> int | None:
    match = re.search(r"(?:way[^0-9]*)?([0-9]+)", str(value))
    return int(match.group(1)) if match else None


def apply(raw: dict) -> tuple[dict, dict]:
    if raw.get("type") != "FeatureCollection":
        raise ValueError("Building input must be a GeoJSON FeatureCollection")
    result = deepcopy(raw)
    features, applied, ignored = [], set(), set()
    for feature in result.get("features", []):
        way_id = _way_id(feature.get("properties", {}).get("osm_id"))
        if way_id in IGNORED:
            ignored.add(way_id)
            continue
        if way_id in HEIGHTS:
            name, height = HEIGHTS[way_id]
            props = feature.setdefault("properties", {})
            props.update(building_name=name, height_m=height,
                         height_source=SOURCE, height_method="user_supplied_estimate",
                         confidence="low", field_verified=False)
            props.pop("height_exclusion_reason", None)
            applied.add(way_id)
        features.append(feature)
    missing = (set(HEIGHTS) - applied) | (IGNORED - ignored)
    if missing:
        raise ValueError(f"Expected OSM ways not found exactly once: {sorted(missing)}")
    result["features"] = features
    metadata = result.setdefault("metadata", {})
    metadata.update(
        source="© OpenStreetMap contributors; user-provided building-height estimates",
        height_estimate_source=SOURCE,
        height_estimate_license_or_permission=(
            "Provided by the user for local project use; underlying redistribution terms not verified"),
        coverage_complete_verified=False,
        coverage_geometry=None,
        quality=("OSM footprints/heights plus user-provided approximate heights; not field verified; "
                 "unnamed roof/tent/shed features excluded from shade obstruction modeling"),
        ignored_unnamed_osm_ways=sorted(IGNORED),
    )
    report = metadata.setdefault("import_report", {})
    report.update(buildings=len(features), user_supplied_height_estimates=len(applied),
                  unknown_heights=0, excluded_unnamed_features=len(ignored),
                  coverage_complete_verified=False)
    return result, {"features": len(features), "applied": len(applied),
                    "ignored": len(ignored), "unknown_heights": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        result, report = apply(raw)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.out), **report}, indent=2))
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, f"Invalid building-height input: {error}\n")


if __name__ == "__main__":
    main()
