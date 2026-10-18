from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


def exporter():
    path = Path(__file__).resolve().parents[2] / "scripts" / "export_field_audit.py"
    spec = spec_from_file_location("export_field_audit", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_field_export_is_explicitly_unverified_and_actionable():
    geometry = SimpleNamespace(
        coordinates=[[-118.444, 34.070], [-118.443, 34.071]],
        model_dump=lambda: {"type": "LineString", "coordinates": geometry.coordinates},
    )
    segment = SimpleNamespace(geometry=geometry, shade_state="shade", duration_s=30)
    route = SimpleNamespace(mode="fastest", geometry=geometry, segments=[segment],
                            duration_s=30, distance_m=40, sun_seconds=0, same_as=None)
    response = SimpleNamespace(routes=[route])

    result = exporter().build_audit_geojson(
        response, origin_id="a", destination_id="b",
        when=datetime.fromisoformat("2026-10-17T15:00:00-07:00"), temperature_c=38,
        building_reach_m=70, tree_reach_m=60,
        candidate_bbox=(-118.445, 34.069, -118.442, 34.072))

    assert result["metadata"]["assumed_coverage_only"] is True
    assert result["metadata"]["coverage_complete_verified"] is False
    assert result["metadata"]["schema_version"] == 1
    assert all(value is None for value in result["metadata"]["review"].values())
    kinds = [feature["properties"]["feature_kind"] for feature in result["features"]]
    assert kinds == ["candidate_route", "modeled_segment", "field_check", "field_check",
                     "field_check", "field_check", "field_check", "inspection_zone"]
    check = result["features"][2]["properties"]
    assert check["actual_state"] is None and check["missing_obstruction"] is None
    zone = result["features"][-1]["properties"]
    assert zone["scope"] == "all_maximum_shade_eligible_edges_bbox"

    buildings = {"features": [{"type": "Feature", "geometry": {
        "type": "Polygon", "coordinates": [[[-118.4441, 34.0699], [-118.4439, 34.0699],
        [-118.4439, 34.0701], [-118.4441, 34.0701], [-118.4441, 34.0699]]]},
        "properties": {"osm_id": "way/1", "height_m": 12}}]}
    trees = {"features": [{"type": "Feature", "geometry": {
        "type": "Point", "coordinates": [-118.4435, 34.0705]},
        "properties": {"tree_id": "tree-1", "height_m": 8, "crown_radius_m": 2}}]}
    exporter().add_obstruction_checks(result, buildings, trees)
    assert result["metadata"]["obstruction_checks"] == {"buildings": 1, "trees": 1}
    objects = [feature for feature in result["features"]
               if feature["properties"]["feature_kind"] in ("building_check", "tree_check")]
    assert all(feature["properties"]["presence_verified"] is None for feature in objects)
    assert all(feature["properties"]["dimensions_verified"] is None for feature in objects)
