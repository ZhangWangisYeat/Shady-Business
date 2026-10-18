from importlib.util import module_from_spec, spec_from_file_location
from datetime import datetime
import json
from pathlib import Path

import networkx as nx
from shapely.geometry import box, mapping


def auditor():
    path = Path(__file__).resolve().parents[2] / "scripts" / "audit_shade_coverage.py"
    spec = spec_from_file_location("audit_shade_coverage", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_inputs(tmp_path, *, complete=True, building_height=12):
    coverage = mapping(box(-118.446, 34.068, -118.442, 34.072))
    buildings = {"type": "FeatureCollection", "metadata": {
        "source": "fixture", "coverage_complete_verified": complete,
        "coverage_geometry": coverage, "source_bbox": [-118.446, 34.068, -118.442, 34.072],
        "import_report": {"buildings": 1}}, "features": [{"type": "Feature",
        "geometry": mapping(box(-118.445, 34.069, -118.4449, 34.0691)),
        "properties": {"height_m": building_height}}]}
    trees = {"type": "FeatureCollection", "metadata": {
        "source": "fixture", "coordinate_reference_system": "EPSG:4326",
        "height_unit": "m", "crown_radius_unit": "m",
        "coverage_complete_verified": complete, "coverage_geometry": coverage,
        "study_bbox": [-118.446, 34.068, -118.442, 34.072],
        "import_report": {"source_rows": 1, "outside_study_rectangle": 0,
                          "invalid_coordinates": 0, "non_tree_records": 0,
                          "standing_tree_records": 1}},
        "features": [{"type": "Feature", "geometry": {
            "type": "Point", "coordinates": [-118.4445, 34.0695]}, "properties": {
            "tree_id": "one", "status": "tree", "height_m": 10, "crown_radius_m": 2}}]}
    buildings_path, trees_path = tmp_path / "buildings.geojson", tmp_path / "trees.geojson"
    buildings_path.write_text(json.dumps(buildings))
    trees_path.write_text(json.dumps(trees))
    return buildings_path, trees_path


def test_audit_requires_complete_dimensions_and_explicit_verified_coverage(tmp_path):
    buildings, trees = write_inputs(tmp_path)
    report = auditor().audit(buildings, trees, (-118.4455, 34.0685, -118.443, 34.071))
    assert report["ready"] and report["blockers"] == []
    assert report["source_accounting"]["buildings"]["consistent"]
    assert report["source_accounting"]["trees"]["source_rows"] == 1
    assert report["source_accounting"]["trees"]["accounted_rows"] == 1

    buildings, trees = write_inputs(tmp_path, complete=False, building_height=None)
    report = auditor().audit(buildings, trees, (-118.4455, 34.0685, -118.443, 34.071))
    assert not report["ready"]
    assert report["buildings"]["unknown_height_manifest"] == [{
        "osm_id": None, "name": None, "height_source": None,
        "intersects_corridor": True,
    }]
    assert {item["code"] for item in report["blockers"]} == {
        "building_unknown_heights", "building_coverage_unverified",
        "tree_coverage_unverified",
    }


def test_route_audit_covers_all_edges_eligible_for_three_modes():
    graph = nx.MultiDiGraph()
    graph.add_node("s", x=-118.445, y=34.070)
    graph.add_node("fast", x=-118.444, y=34.070)
    graph.add_node("shade", x=-118.444, y=34.071)
    graph.add_node("t", x=-118.443, y=34.070)
    graph.add_edge("s", "fast", key="sf", length=300)
    graph.add_edge("fast", "t", key="ft", length=300)
    graph.add_edge("s", "shade", key="ss", length=450)
    graph.add_edge("shade", "t", key="st", length=450)

    report = auditor().route_candidate_envelopes(
        graph, (-118.445, 34.070), (-118.443, 34.070))

    assert report["recommended"]["eligible_edges"] == 2
    assert report["maximum_shade"]["eligible_edges"] == 4
    assert report["maximum_shade"]["bbox"] == [-118.445, 34.07, -118.443, 34.071]


def test_shadow_input_extent_includes_time_specific_caster_buffer(tmp_path):
    buildings, trees = write_inputs(tmp_path)
    report = auditor().shadow_input_extent(
        buildings, trees, (-118.4455, 34.0685, -118.443, 34.071),
        datetime.fromisoformat("2026-10-17T12:00:00-07:00"))

    assert report["status"] == "checked"
    assert report["buildings"]["max_shadow_reach_m"] > 0
    assert report["buildings"]["contains_buffered_candidates"]
    assert report["trees"]["contains_buffered_candidates"]
