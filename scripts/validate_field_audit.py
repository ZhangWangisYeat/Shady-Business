#!/usr/bin/env python3
"""Validate completed field evidence without changing runtime shade coverage."""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from math import isfinite
from pathlib import Path


MODES = {"fastest", "recommended", "maximum_shade"}
EDITABLE_FIELDS = {
    "presence_verified", "dimensions_verified", "actual_state",
    "missing_obstruction", "photo_reference", "notes",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def structure_sha256(audit: dict) -> str:
    structural = deepcopy(audit)
    metadata = structural.get("metadata", {})
    metadata.pop("review", None)
    metadata.pop("structure_sha256", None)
    for feature in structural.get("features", []):
        properties = feature.get("properties", {})
        for field in EDITABLE_FIELDS:
            properties.pop(field, None)
    canonical = json.dumps(
        structural, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate(audit: dict, inputs: dict[str, Path]) -> dict:
    blockers = []

    def block(code: str, count: int | None = None) -> None:
        item = {"code": code}
        if count is not None:
            item["count"] = count
        blockers.append(item)

    if not isinstance(audit, dict):
        audit = {}
    metadata = audit.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    features = audit.get("features", [])
    if audit.get("type") != "FeatureCollection" or not isinstance(features, list):
        block("invalid_feature_collection")
        features = []

    def properties(feature: object) -> dict:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            return {}
        return feature["properties"]

    if metadata.get("schema_version") != 1:
        block("unsupported_schema_version")
    if (metadata.get("assumed_coverage_only") is not True
            or metadata.get("not_runtime_shade_input") is not True
            or metadata.get("coverage_complete_verified") is not False):
        block("unsafe_audit_metadata")
    try:
        if metadata.get("structure_sha256") != structure_sha256(audit):
            block("audit_structure_mismatch")
    except (AttributeError, TypeError, ValueError):
        block("audit_structure_invalid")

    recorded_inputs = metadata.get("inputs", {})
    if not isinstance(recorded_inputs, dict):
        recorded_inputs = {}
    for name, path in inputs.items():
        recorded = recorded_inputs.get(name, {})
        if not isinstance(recorded, dict):
            recorded = {}
        if recorded.get("sha256") != file_sha256(path):
            block(f"{name}_input_hash_mismatch")

    review = metadata.get("review", {})
    if not isinstance(review, dict):
        review = {}
    for field in ("review_reference", "review_method"):
        if not isinstance(review.get(field), str) or not review[field].strip():
            block(f"{field}_missing")
    try:
        reviewed_at = datetime.fromisoformat(review.get("reviewed_at", ""))
        if reviewed_at.utcoffset() is None:
            raise ValueError
    except (TypeError, ValueError):
        block("reviewed_at_invalid")
    for field in ("inspection_zone_complete", "outside_shadow_casters_checked",
                  "source_reuse_authorized"):
        if review.get(field) is not True:
            block(f"{field}_not_confirmed")

    by_kind = {}
    for feature in features:
        kind = properties(feature).get("feature_kind")
        by_kind.setdefault(kind, []).append(feature)

    zones = by_kind.get("inspection_zone", [])
    if len(zones) != 1 or properties(zones[0]).get("scope") != (
            "all_maximum_shade_eligible_edges_bbox"):
        block("candidate_inspection_zone_invalid")
    route_modes = {properties(feature).get("mode")
                   for feature in by_kind.get("candidate_route", [])}
    if route_modes != MODES:
        block("candidate_routes_incomplete")
    route_scope = metadata.get("route_scope", {})
    input_extent = metadata.get("input_extent", {})
    try:
        bbox = route_scope["maximum_shade"]["bbox"]
        bbox_valid = (len(bbox) == 4 and all(
            not isinstance(value, bool) and isfinite(float(value)) for value in bbox)
            and float(bbox[0]) < float(bbox[2]) and float(bbox[1]) < float(bbox[3]))
        extent_valid = (input_extent.get("status") == "checked" and all(
            input_extent[source].get("contains_buffered_candidates") is True
            for source in ("buildings", "trees")))
        if not bbox_valid or not extent_valid:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        block("coverage_scope_invalid")

    objects = by_kind.get("building_check", []) + by_kind.get("tree_check", [])
    expected = metadata.get("obstruction_checks", {})
    if not isinstance(expected, dict):
        expected = {}
    if (expected.get("buildings") != len(by_kind.get("building_check", []))
            or expected.get("trees") != len(by_kind.get("tree_check", []))):
        block("obstruction_count_mismatch")
    missing_presence = sum(
        properties(feature).get("presence_verified") is not True
        for feature in objects)
    missing_dimensions = sum(
        properties(feature).get("dimensions_verified") is not True
        for feature in objects)
    if missing_presence:
        block("obstruction_presence_unverified", missing_presence)
    if missing_dimensions:
        block("obstruction_dimensions_unverified", missing_dimensions)
    invalid_dimensions = 0
    for feature in objects:
        values = [properties(feature).get("height_m")]
        if properties(feature).get("feature_kind") == "tree_check":
            values.append(properties(feature).get("crown_radius_m"))
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not isfinite(value) or value <= 0 for value in values):
            invalid_dimensions += 1
    if invalid_dimensions:
        block("obstruction_dimensions_invalid", invalid_dimensions)

    checks = by_kind.get("field_check", [])
    mode_counts = {mode: sum(properties(check).get("mode") == mode
                             for check in checks) for mode in MODES}
    if any(count != 5 for count in mode_counts.values()):
        block("field_check_count_invalid")
    ids = [properties(check).get("audit_id") for check in checks]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        block("field_check_ids_invalid")
    missing_actual = mismatch = missing_obstruction_review = missing_photo = 0
    for check in checks:
        check_properties = properties(check)
        actual = check_properties.get("actual_state")
        expected_state = check_properties.get("expected_state")
        if actual not in {"sun", "shade"}:
            missing_actual += 1
        elif actual != expected_state:
            mismatch += 1
        if check_properties.get("missing_obstruction") is not False:
            missing_obstruction_review += 1
        photo = check_properties.get("photo_reference")
        if not isinstance(photo, str) or not photo.strip():
            missing_photo += 1
    for code, count in (
        ("field_state_unverified", missing_actual),
        ("modeled_state_mismatch", mismatch),
        ("missing_obstruction_not_cleared", missing_obstruction_review),
        ("photo_reference_missing", missing_photo),
    ):
        if count:
            block(code, count)

    return {
        "ready_for_manual_promotion": not blockers,
        "coverage_promoted": False,
        "counts": {
            "buildings": len(by_kind.get("building_check", [])),
            "trees": len(by_kind.get("tree_check", [])),
            "field_checks": len(checks),
        },
        "blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--buildings", type=Path, required=True)
    parser.add_argument("--trees", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    args = parser.parse_args()
    try:
        audit = json.loads(args.audit.read_text(encoding="utf-8"))
        report = validate(audit, {
            "buildings": args.buildings, "trees": args.trees, "graph": args.graph,
        })
    except (OSError, json.JSONDecodeError) as error:
        parser.exit(2, f"Cannot validate field audit: {error}\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready_for_manual_promotion"] else 1)


if __name__ == "__main__":
    main()
