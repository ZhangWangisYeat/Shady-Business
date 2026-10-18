"""Synthetic crown geometry and pipeline tests, not field-accuracy assertions."""
from copy import deepcopy
import csv
from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from math import cos, pi, radians, sin, sqrt, tan
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import Point, box, mapping

from app.shade import model as shade_model
from app.shade.model import INVERSE_PROJECTION, PROJECTION, ShadeModel, build_shadow_field, with_tree_file
from app.shade.scoring import RouteEdge, score_route
from app.shade.trees import TreeCrown, cast_tree_shadow, read_tree_model

X, Y = PROJECTION.transform(-118.4452, 34.0689)
WHEN = datetime.fromisoformat("2026-10-17T15:00:00-07:00")


def crown(height=10, radius=2, base=None):
    return TreeCrown(Point(X, Y), height, radius, "synthetic-tree", base)


def tree_file(tmp_path, **changes):
    data = {"type": "FeatureCollection", "metadata": {
        "source": "synthetic tree fixture", "data_as_of": None,
        "coordinate_reference_system": "EPSG:4326", "height_unit": "m", "crown_radius_unit": "m"},
        "features": [{"type": "Feature", "geometry": {
            "type": "Point", "coordinates": [-118.4452, 34.0689]}, "properties": {
            "tree_id": "fixture", "status": "tree", "height_m": 10, "crown_radius_m": 2}}]}
    data["features"][0]["properties"].update(changes)
    path = tmp_path / "trees.geojson"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("azimuth,offset", [(90, (-8, 0)), (270, (8, 0)), (0, (0, -8)), (180, (0, 8))])
def test_tree_shadow_moves_away_from_sun(azimuth, offset):
    shadow = cast_tree_shadow(crown(), 45, azimuth)
    assert (shadow.centroid.x - X, shadow.centroid.y - Y) == pytest.approx(offset, abs=1e-7)
    assert shadow.area == pytest.approx(pi * sqrt(8) * 2, rel=.001)
    assert not shadow.covers(Point(X, Y))  # A floating crown is not a building wall.


def test_tree_at_zenith_and_measured_crown_base():
    overhead = cast_tree_shadow(crown(), 90, 90)
    assert overhead.bounds == pytest.approx((X - 2, Y - 2, X + 2, Y + 2))
    assert overhead.area == pytest.approx(pi * 4, rel=.001)
    measured = cast_tree_shadow(crown(base=2), 45, 90)
    assert measured.centroid.x - X == pytest.approx(-6, abs=1e-7)
    assert measured.bounds[2] - measured.bounds[0] == pytest.approx(2 * sqrt(20), rel=.001)


def test_short_wide_crown_never_extends_below_ground():
    shadow = cast_tree_shadow(crown(height=1, radius=5), 45, 90)
    assert shadow.centroid.x - X == pytest.approx(-.5, abs=1e-7)
    assert shadow.area > 0 and shadow.is_valid


@pytest.mark.parametrize("elevation,azimuth", [(15, 30), (60, 140)])
def test_ellipse_contains_independently_projected_3d_crown_surface(elevation, azimuth):
    # Project a mesh of 3D ellipsoid points along parallel sun rays, independent
    # of the analytic ellipse construction. Polygonization uses 128 vertices.
    shadow = cast_tree_shadow(crown(), elevation, azimuth).buffer(.01)
    for i in range(17):
        polar = pi * i / 16
        for j in range(32):
            angle = 2 * pi * j / 32
            x, y, z = 2 * sin(polar) * cos(angle), 2 * sin(polar) * sin(angle), 8 + 2 * cos(polar)
            reach = z / tan(radians(elevation))
            assert shadow.covers(Point(X + x - reach * sin(radians(azimuth)),
                                       Y + y - reach * cos(radians(azimuth))))


@pytest.mark.parametrize("height,radius,base,elevation", [
    (0, 2, None, 45), (10, 0, None, 45), (float("nan"), 2, None, 45),
    (10, 2, -1, 45), (10, 2, 10, 45), (10, 2, None, 0), (10, 2, None, 2),
    (10, 2, None, 91), (10, 2, True, 45),
])
def test_invalid_crown_not_defaulted(height, radius, base, elevation):
    with pytest.raises(ValueError):
        cast_tree_shadow(crown(height, radius, base), elevation, 90)


def test_tree_only_model_and_shade_scoring(tmp_path, monkeypatch):
    model = with_tree_file(None, tree_file(tmp_path))
    monkeypatch.setattr(shade_model, "solar_angles", lambda when: (45, 90))
    field = build_shadow_field(model, WHEN)
    coords = tuple(INVERSE_PROJECTION.transform(X + x, Y) for x in (-15, 0))
    result = score_route([RouteEdge(coords, 15)], field)
    assert [s.shade_state for s in result.segments] == ["unknown", "shade", "unknown"]
    assert result.shade_seconds == pytest.approx(2 * sqrt(8), rel=.001)
    assert result.sun_seconds is None and result.unknown_seconds > 0
    assert result.shade_seconds + result.unknown_seconds == pytest.approx(15)
    assert "synthetic tree fixture" in result.source
    assert any("ellipsoid" in note for note in result.limitations)


def test_building_and_tree_union_never_counts_overlap_twice(monkeypatch):
    monkeypatch.setattr(shade_model, "solar_angles", lambda when: (45, 90))
    tree = crown()
    building = ((box(X - 9, Y - 1, X - 7, Y + 1), 1),)
    tree_only = build_shadow_field(ShadeModel((), None, False, trees=(tree,)), WHEN)
    building_only = build_shadow_field(ShadeModel(building, None, False), WHEN)
    combined = build_shadow_field(ShadeModel(building, None, False, trees=(tree,)), WHEN)
    assert combined.shadows.area <= tree_only.shadows.area + building_only.shadows.area
    assert combined.shadows.area < tree_only.shadows.area + building_only.shadows.area - 1
    assert combined.shadows.covers(tree_only.shadows) and combined.shadows.covers(building_only.shadows)


def test_combined_coverage_is_verified_intersection_only(tmp_path):
    path = tree_file(tmp_path)
    raw = json.loads(path.read_text())
    tree_coverage = box(-118.446, 34.068, -118.444, 34.070)
    raw["metadata"].update(coverage_complete_verified=True,
                           coverage_geometry=mapping(tree_coverage))
    path.write_text(json.dumps(raw))
    building_coverage = shade_model._project_polygon(
        mapping(box(-118.4455, 34.0685, -118.4435, 34.0705)))
    buildings = ShadeModel((), None, True, building_coverage, "buildings")
    combined = with_tree_file(buildings, path)
    expected = building_coverage.intersection(shade_model._project_polygon(mapping(tree_coverage)))
    assert combined.coverage_complete_verified
    assert combined.coverage_geometry.equals(expected)

    raw["metadata"]["coverage_complete_verified"] = False
    path.write_text(json.dumps(raw))
    incomplete = with_tree_file(buildings, path)
    assert not incomplete.coverage_complete_verified and incomplete.coverage_geometry is None


@pytest.mark.parametrize("props", [{"height_m": 0}, {"crown_radius_m": None}, {"status": "stump"}, {"height_m": True}])
def test_incomplete_or_non_tree_records_never_become_crowns(tmp_path, props):
    dataset = read_tree_model(tree_file(tmp_path, **props))
    assert dataset.trees == () and dataset.unmodeled_records == 1
    assert with_tree_file(None, tree_file(tmp_path, **props)) is None


def test_tree_metadata_units_crs_duplicates_are_validated(tmp_path):
    path = tree_file(tmp_path)
    original = json.loads(path.read_text())
    for key, bad_value in (("height_unit", "ft"), ("crown_radius_unit", None), ("coordinate_reference_system", "EPSG:26911")):
        raw = deepcopy(original)
        raw["metadata"][key] = bad_value
        path.write_text(json.dumps(raw))
        with pytest.raises(ValueError):
            read_tree_model(path)
    raw = deepcopy(original)
    raw["features"].append(deepcopy(raw["features"][0]))
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="unique"):
        read_tree_model(path)
    raw = deepcopy(original)
    raw["features"][0]["geometry"]["coordinates"] = [34.0689, -118.4452]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        read_tree_model(path)


def test_default_loader_combines_trees_and_resets_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(shade_model, "SHADE_FILE", tmp_path / "missing-buildings.geojson")
    monkeypatch.setattr(shade_model, "TREE_FILE", tree_file(tmp_path))
    shade_model.load_model.cache_clear()
    try:
        assert len(shade_model.load_model().trees) == 1
    finally:
        shade_model.load_model.cache_clear()


def importer():
    spec = spec_from_file_location("arborpro_tree_importer", Path(__file__).resolve().parents[2] / "scripts" / "import_arborpro_trees.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def csv_file(tmp_path):
    path = tmp_path / "inventory.csv"
    rows = [
        ["one", 34.069, -118.444, "1", "1", 40, 20],
        ["stump", 34.069, -118.444, "2", "2", 1, 0],
        ["vacant", 34.069, -118.444, "3", "3", 0, 0],
        ["unknown", 34.069, -118.444, "4", "1", 0, 0],
        ["outside", 33.77, -118.3, "5", "1", 40, 20],
        ["badgps", "nan", -118.444, "6", "1", 40, 20],
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["globalid", "latitude", "longitude", "Tree ID", "Status", "Height (feet)", "Crown (feet)"])
        writer.writerows(rows)
    return path


def test_arborpro_units_filtering_missing_measurements_and_provenance(tmp_path):
    data, report = importer().normalize_inventory(csv_file(tmp_path), (-118.448, 34.0675, -118.438, 34.0755))
    assert report == dict(source_rows=6, outside_study_rectangle=1, invalid_coordinates=1,
                          non_tree_records=2, standing_tree_records=2, model_ready=1,
                          missing_height=1, missing_crown=1)
    first, unknown = [f["properties"] for f in data["features"]]
    assert first["height_m"] == pytest.approx(12.192)
    assert first["crown_radius_m"] == pytest.approx(3.048)
    assert unknown["height_m"] is None and unknown["crown_radius_m"] is None
    assert data["metadata"]["coverage_complete_verified"] is False
    assert data["metadata"]["data_as_of"] is None
    assert data["metadata"]["source_file_checksum"].startswith("sha256:")
    output = tmp_path / "normalized.geojson"
    output.write_text(json.dumps(data))
    assert len(read_tree_model(output).trees) == 1


def test_importer_rejects_duplicate_ids_and_bad_bbox(tmp_path):
    path = csv_file(tmp_path)
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(["one", 34.069, -118.444, "1", "1", 40, 20])
    with pytest.raises(ValueError, match="unique"):
        importer().normalize_inventory(path, (-118.448, 34.0675, -118.438, 34.0755))
    with pytest.raises(ValueError, match="bbox"):
        importer().normalize_inventory(path, (34, -118, 35, -117))
    path = csv_file(tmp_path)
    with path.open("a", encoding="utf-8", newline="") as handle:
        # Short CSV row: missing status must not become a standing tree.
        csv.writer(handle).writerow(["missingstatus", 34.069, -118.444, "7"])
    _, report = importer().normalize_inventory(path, (-118.448, 34.0675, -118.438, 34.0755))
    assert report["non_tree_records"] == 3


def test_tree_shade_reaches_existing_route_api_without_schema_change(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routing import service

    model = with_tree_file(None, tree_file(tmp_path))
    monkeypatch.setattr(shade_model, "solar_angles", lambda when: (45, 90))
    start, end = [INVERSE_PROJECTION.transform(X + x, Y) for x in (-8.5, -7.5)]
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=start[0], y=start[1])
    graph.add_node("b", x=end[0], y=end[1])
    graph.add_edge("a", "b", length=1.)
    monkeypatch.setattr(service, "load_graph", lambda: graph)
    monkeypatch.setattr(service, "load_model", lambda: model)
    result = TestClient(app).post("/api/routes", json={"origin": {"coordinate": start},
        "destination": {"coordinate": end}, "departure_time": WHEN.isoformat(), "temperature_c": 29})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["conditions"]["shade_model"] == "geometry_estimate"
    assert data["conditions"]["shade_coverage"] == "unverified"
    assert data["conditions"]["solar_status"] == "daylight"
    assert any("ellipsoid" in note for note in data["conditions"]["model_limitations"])
    for route in data["routes"]:
        assert route["sun_seconds"] == 0 and route["unknown_seconds"] == 0
        assert route["coverage_fraction"] == 1
        assert route["segments"][0]["shade_state"] == "shade"
        assert sum(s["duration_s"] for s in route["segments"]) == pytest.approx(route["duration_s"], abs=.01)


@pytest.mark.parametrize("solar_elevation,states,sun_known", [
    (45, ["unknown", "shade", "unknown"], False),
    (-5, ["unknown"], True),
    (1, ["unknown"], False),
])
def test_route_api_splits_mixed_crowns_and_preserves_night_contract(tmp_path, monkeypatch, solar_elevation, states, sun_known):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routing import service

    model = with_tree_file(None, tree_file(tmp_path))
    monkeypatch.setattr(shade_model, "solar_angles", lambda when: (solar_elevation, 90))
    start, end = [INVERSE_PROJECTION.transform(X + x, Y) for x in (-15, 0)]
    graph = nx.MultiDiGraph()
    graph.add_node("a", x=start[0], y=start[1])
    graph.add_node("b", x=end[0], y=end[1])
    graph.add_edge("a", "b", length=15.)
    monkeypatch.setattr(service, "load_graph", lambda: graph)
    monkeypatch.setattr(service, "load_model", lambda: model)
    response = TestClient(app).post("/api/routes", json={"origin": {"coordinate": start},
        "destination": {"coordinate": end}, "departure_time": WHEN.isoformat(), "temperature_c": 29})
    assert response.status_code == 200
    data = response.json()
    expected_solar_status = "daylight" if solar_elevation == 45 else "night" if solar_elevation < 0 else "low_sun"
    assert data["conditions"]["solar_status"] == expected_solar_status
    assert data["conditions"]["shade_coverage"] == "unverified"
    for route in data["routes"]:
        assert [s["shade_state"] for s in route["segments"]] == states
        assert (route["sun_seconds"] is not None) is sun_known
        assert sum(s["unknown_seconds"] for s in route["segments"]) == pytest.approx(route["unknown_seconds"], abs=.01)
        assert sum(s["duration_s"] for s in route["segments"]) == pytest.approx(route["duration_s"], abs=.01)
        assert route["coverage_fraction"] == pytest.approx(
            1 - route["unknown_seconds"] / route["duration_s"], abs=1e-4)
        if sun_known:
            assert route["sun_seconds"] == 0 and route["unknown_seconds"] == 0


def test_local_cli_accepts_tree_only_data(tmp_path, monkeypatch, capsys):
    import sys
    spec = spec_from_file_location("tree_scoring_cli", Path(__file__).resolve().parents[2] / "scripts" / "score_route_shade.py")
    cli = module_from_spec(spec)
    spec.loader.exec_module(cli)
    coords = [INVERSE_PROJECTION.transform(X + x, Y) for x in (-15, 0)]
    route = tmp_path / "route.json"
    route.write_text(json.dumps({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords},
                                 "properties": {"duration_s": 15}}))
    monkeypatch.setattr(shade_model, "solar_angles", lambda when: (45, 90))
    monkeypatch.setattr(sys, "argv", ["score_route_shade.py", "--route", str(route),
        "--trees", str(tree_file(tmp_path)), "--departure", WHEN.isoformat()])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["shade_seconds"] > 0 and result["sun_seconds"] is None
    assert "synthetic tree fixture" in result["source"]


def test_shadow_field_cut_to_an_area_matches_inside_it_and_claims_nothing_outside():
    from datetime import timezone, timedelta
    from app.shade.model import ShadeModel, build_shadow_field
    from app.shade.trees import TreeCrown
    # a row of trees from x=0 to x=2000 m; the area is a small box in the middle
    trees = tuple(TreeCrown(Point(x, 0), 15.0, 4.0, f"t{x}") for x in range(0, 2001, 40))
    model = ShadeModel((), None, True, box(-100, -100, 2100, 100), "fixture", trees)
    when = datetime(2026, 10, 18, 13, 0, tzinfo=timezone(timedelta(hours=-7)))
    area = box(900, -50, 1100, 50)
    full, cut = build_shadow_field(model, when), build_shadow_field(model, when, area)
    assert full.shadows.intersection(area).symmetric_difference(cut.shadows.intersection(area)).area < 1e-6
    assert cut.coverage_geometry.equals(area)
    assert cut.shadows.area < full.shadows.area / 3
