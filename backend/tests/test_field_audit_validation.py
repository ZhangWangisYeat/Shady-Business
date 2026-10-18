from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json


def validator():
    path = Path(__file__).resolve().parents[2] / "scripts" / "validate_field_audit.py"
    spec = spec_from_file_location("validate_field_audit", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def promoter():
    path = Path(__file__).resolve().parents[2] / "scripts" / "promote_field_audit.py"
    spec = spec_from_file_location("promote_field_audit", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_fixture(tmp_path):
    module = validator()
    inputs = {}
    for name in ("buildings", "trees", "graph"):
        path = tmp_path / name
        content = (json.dumps({"type": "FeatureCollection", "metadata": {}, "features": []})
                   if name in {"buildings", "trees"} else name)
        path.write_text(content, encoding="utf-8")
        inputs[name] = path
    metadata = {
        "schema_version": 1,
        "assumed_coverage_only": True,
        "coverage_complete_verified": False,
        "not_runtime_shade_input": True,
        "inputs": {name: {"sha256": module.file_sha256(path)}
                   for name, path in inputs.items()},
        "review": {
            "review_reference": "field-log-1",
            "reviewed_at": "2026-10-17T15:30:00-07:00",
            "review_method": "on-foot inspection",
            "inspection_zone_complete": True,
            "outside_shadow_casters_checked": True,
            "source_reuse_authorized": True,
        },
        "obstruction_checks": {"buildings": 1, "trees": 1},
        "route_scope": {"maximum_shade": {
            "bbox": [-118.445, 34.069, -118.442, 34.072],
        }},
        "input_extent": {
            "status": "checked",
            "buildings": {"contains_buffered_candidates": True},
            "trees": {"contains_buffered_candidates": True},
        },
    }
    features = [{"type": "Feature", "geometry": None, "properties": {
        "feature_kind": "inspection_zone",
        "scope": "all_maximum_shade_eligible_edges_bbox",
    }}]
    for mode in module.MODES:
        features.append({"type": "Feature", "geometry": None, "properties": {
            "feature_kind": "candidate_route", "mode": mode,
        }})
        for index in range(5):
            state = "sun" if index == 0 else "shade"
            features.append({"type": "Feature", "geometry": None, "properties": {
                "feature_kind": "field_check", "mode": mode,
                "audit_id": f"{mode}-{index}", "expected_state": state,
                "actual_state": state, "missing_obstruction": False,
                "photo_reference": f"photo-{mode}-{index}.jpg",
            }})
    for kind in ("building_check", "tree_check"):
        dimensions = ({"height_m": 12} if kind == "building_check"
                      else {"height_m": 8, "crown_radius_m": 2})
        features.append({"type": "Feature", "geometry": None, "properties": {
            "feature_kind": kind, "presence_verified": True,
            "dimensions_verified": True, **dimensions,
        }})
    audit = {"type": "FeatureCollection", "metadata": metadata, "features": features}
    audit["metadata"]["structure_sha256"] = module.structure_sha256(audit)
    return module, audit, inputs


def test_complete_evidence_is_ready_but_never_promoted(tmp_path):
    module, audit, inputs = audit_fixture(tmp_path)
    report = module.validate(audit, inputs)
    assert report == {
        "ready_for_manual_promotion": True,
        "coverage_promoted": False,
        "counts": {"buildings": 1, "trees": 1, "field_checks": 15},
        "blockers": [],
    }


def test_incomplete_or_stale_evidence_fails_closed(tmp_path):
    module, audit, inputs = audit_fixture(tmp_path)
    audit["metadata"]["review"]["inspection_zone_complete"] = None
    audit["features"][-1]["properties"]["dimensions_verified"] = None
    check = next(feature for feature in audit["features"]
                 if feature["properties"]["feature_kind"] == "field_check")
    check["properties"]["actual_state"] = None
    check["properties"]["photo_reference"] = None
    inputs["graph"].write_text("changed", encoding="utf-8")

    report = module.validate(audit, inputs)
    assert not report["ready_for_manual_promotion"]
    assert not report["coverage_promoted"]
    assert {blocker["code"] for blocker in report["blockers"]} == {
        "graph_input_hash_mismatch", "inspection_zone_complete_not_confirmed",
        "obstruction_dimensions_unverified", "field_state_unverified",
        "photo_reference_missing",
    }


def test_malformed_packet_reports_blockers_instead_of_crashing(tmp_path):
    module, _, inputs = audit_fixture(tmp_path)
    report = module.validate([], inputs)
    assert not report["ready_for_manual_promotion"]
    assert "invalid_feature_collection" in {
        blocker["code"] for blocker in report["blockers"]
    }


def test_route_scope_tampering_is_rejected(tmp_path):
    module, audit, inputs = audit_fixture(tmp_path)
    audit["metadata"]["route_scope"]["maximum_shade"]["bbox"][0] -= 0.01
    report = module.validate(audit, inputs)
    assert "audit_structure_mismatch" in {
        blocker["code"] for blocker in report["blockers"]
    }


def test_promotion_creates_derived_inputs_only_after_validation(tmp_path):
    _, audit, inputs = audit_fixture(tmp_path)
    audit["metadata"].update(
        origin_place_id="powell-library", destination_place_id="ackerman-union",
        departure_time="2026-10-17T15:00:00-07:00",
    )
    # These provenance fields are structural, so refresh before field evidence is sealed.
    audit["metadata"]["structure_sha256"] = validator().structure_sha256(audit)
    audit_path = tmp_path / "audit.geojson"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    out_buildings = tmp_path / "verified-buildings.geojson"
    out_trees = tmp_path / "verified-trees.geojson"
    originals = {name: path.read_text(encoding="utf-8") for name, path in inputs.items()}

    report = promoter().promote(
        audit_path=audit_path, buildings_path=inputs["buildings"],
        trees_path=inputs["trees"], graph_path=inputs["graph"],
        out_buildings=out_buildings, out_trees=out_trees, confirmed=True,
    )

    assert report["promoted"]
    assert all(path.read_text(encoding="utf-8") == originals[name]
               for name, path in inputs.items())
    for output in (out_buildings, out_trees):
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["metadata"]["coverage_complete_verified"] is True
        assert data["metadata"]["coverage_geometry"]["type"] == "Polygon"
        assert data["metadata"]["coverage_evidence"]["type"] == "field_audit_v1"


def test_promotion_refuses_incomplete_audit_without_writing(tmp_path):
    module, audit, inputs = audit_fixture(tmp_path)
    audit["metadata"]["review"]["inspection_zone_complete"] = None
    audit_path = tmp_path / "audit.geojson"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    out_buildings = tmp_path / "verified-buildings.geojson"
    out_trees = tmp_path / "verified-trees.geojson"

    report = promoter().promote(
        audit_path=audit_path, buildings_path=inputs["buildings"],
        trees_path=inputs["trees"], graph_path=inputs["graph"],
        out_buildings=out_buildings, out_trees=out_trees, confirmed=True,
    )

    assert not report["promoted"]
    assert not out_buildings.exists() and not out_trees.exists()
