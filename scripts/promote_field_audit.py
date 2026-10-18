#!/usr/bin/env python3
"""Create derived verified-coverage inputs from a completed field audit."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_field_audit import file_sha256, validate


def coverage_polygon(bbox: list[float]) -> dict:
    west, south, east, north = (float(value) for value in bbox)
    return {"type": "Polygon", "coordinates": [[
        [west, south], [east, south], [east, north], [west, north], [west, south],
    ]]}


def promote(*, audit_path: Path, buildings_path: Path, trees_path: Path,
            graph_path: Path, out_buildings: Path, out_trees: Path,
            confirmed: bool) -> dict:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    inputs = {"buildings": buildings_path, "trees": trees_path, "graph": graph_path}
    validation = validate(audit, inputs)
    report = {"promoted": False, "validation": validation}
    if not validation["ready_for_manual_promotion"]:
        return report
    if not confirmed:
        report["blocker"] = "explicit_confirmation_required"
        return report

    output_pairs = ((buildings_path, out_buildings), (trees_path, out_trees))
    if any(source.resolve() == output.resolve() for source, output in output_pairs):
        raise ValueError("Promotion outputs must not overwrite source inputs")
    if out_buildings.resolve() == out_trees.resolve():
        raise ValueError("Building and tree promotion outputs must be different")
    if any(output.exists() for _, output in output_pairs):
        raise ValueError("Promotion output already exists")

    metadata = audit["metadata"]
    bbox = metadata["route_scope"]["maximum_shade"]["bbox"]
    coverage = coverage_polygon(bbox)
    evidence = {
        "type": "field_audit_v1",
        "audit_sha256": file_sha256(audit_path),
        "audit_structure_sha256": metadata["structure_sha256"],
        "review_reference": metadata["review"]["review_reference"],
        "reviewed_at": metadata["review"]["reviewed_at"],
        "origin_place_id": metadata.get("origin_place_id"),
        "destination_place_id": metadata.get("destination_place_id"),
        "departure_time": metadata.get("departure_time"),
    }

    derived = []
    for name, source, output in (
        ("buildings", buildings_path, out_buildings),
        ("trees", trees_path, out_trees),
    ):
        data = json.loads(source.read_text(encoding="utf-8"))
        source_metadata = data.get("metadata")
        if not isinstance(source_metadata, dict):
            raise ValueError(f"{name} input has no metadata object")
        source_metadata.update(
            coverage_complete_verified=True,
            coverage_geometry=coverage,
            coverage_evidence={**evidence, "validated_input_sha256": file_sha256(source)},
        )
        derived.append((data, output))

    prepared = []
    for data, output in derived:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        prepared.append((temporary, output))
    for temporary, output in prepared:
        temporary.replace(output)

    report.update(promoted=True, outputs={
        "buildings": str(out_buildings), "trees": str(out_trees),
    }, coverage_geometry=coverage)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--buildings", type=Path, required=True)
    parser.add_argument("--trees", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--out-buildings", type=Path, required=True)
    parser.add_argument("--out-trees", type=Path, required=True)
    parser.add_argument("--confirm-promotion", action="store_true")
    args = parser.parse_args()
    try:
        report = promote(
            audit_path=args.audit, buildings_path=args.buildings, trees_path=args.trees,
            graph_path=args.graph, out_buildings=args.out_buildings,
            out_trees=args.out_trees, confirmed=args.confirm_promotion,
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"Cannot promote field audit: {error}\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["promoted"] else 1)


if __name__ == "__main__":
    main()
