#!/usr/bin/env python3
"""Import an existing Shady Business OSM bundle as a local building shade input.

No network access. Preserve all footprints but never reuse default or level-based
heights as OSM height tags. Tree crown approximations in old bundles are excluded.
The generated file is local geodata, not a newly licensed or field-verified asset.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from math import isfinite
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.shade.model import _project_polygon


def prepare_buildings(raw: dict, checksum: str) -> tuple[dict, dict]:
    metadata = raw.get("metadata", {})
    if metadata.get("mode") != "osm" or metadata.get("license") != "ODbL 1.0":
        raise ValueError("Expected an OSM bundle with explicit ODbL 1.0 provenance")
    features = []
    usable_heights = 0
    for original in raw.get("buildings", []):
        if original.get("type") != "Feature":
            raise ValueError("Each building must be a GeoJSON Feature")
        _project_polygon(original["geometry"])
        feature = deepcopy(original)
        properties = feature.setdefault("properties", {})
        height = properties.get("height_m")
        # This bundle format records the origin of the already-parsed meter value.
        # Do not promote either assumed heights or level estimates to known heights.
        has_tag = properties.get("height_source") == "OSM height tag (unverified)"
        usable = (has_tag and isinstance(height, (int, float)) and not isinstance(height, bool)
                  and isfinite(height) and 1 <= height <= 250)
        properties["height_m"] = float(height) if usable else None
        properties["height_method"] = "osm_height" if usable else "unknown"
        properties["source"] = metadata.get("source", "OpenStreetMap contributors")
        properties["license"] = "ODbL 1.0"
        properties["field_verified"] = False
        if not usable:
            properties["height_exclusion_reason"] = "Missing OSM height tag; defaults/levels are not accepted by this importer"
        usable_heights += usable
        features.append(feature)
    if not features:
        raise ValueError("Bundle contains no building footprints")
    report = {
        "buildings": len(features), "usable_osm_height_tags": usable_heights,
        "unknown_heights": len(features) - usable_heights,
        "excluded_tree_or_wood_features": len(raw.get("trees", [])),
        "coverage_complete_verified": False,
    }
    output = {"type": "FeatureCollection", "metadata": {
        "source": metadata.get("source", "OpenStreetMap contributors"),
        "source_url": "https://www.openstreetmap.org/",
        "license": "ODbL 1.0", "license_url": "https://www.openstreetmap.org/copyright",
        "coordinate_reference_system": "EPSG:4326", "height_unit": "m",
        "retrieved_at": metadata.get("fetched_at"),
        "data_as_of": None,  # Download time is not survey time.
        "source_file_checksum": checksum, "source_bbox": metadata.get("bbox"),
        "coverage_complete_verified": False, "coverage_geometry": None,
        "quality": "OSM heights unverified; no default heights or modeled tree crowns imported",
        "import_report": report,
    }, "features": features}
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.out.resolve():
            raise ValueError("Output must not overwrite the source bundle")
        source = args.input.read_bytes()
        data, report = prepare_buildings(json.loads(source), "sha256:" + hashlib.sha256(source).hexdigest())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(data, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.out), **report}, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, f"Invalid OSM building input: {error}\n")


if __name__ == "__main__":
    main()
