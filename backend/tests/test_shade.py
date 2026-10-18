"""Synthetic metric fixtures, NOT UCLA observations or accuracy evidence."""
import json
from datetime import datetime, timezone
from math import tan, radians
from zoneinfo import ZoneInfo

import pytest
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import transform, unary_union

from app.shade import model as shade_model
from app.shade.model import (
    INVERSE_PROJECTION, PROJECTION, ShadeModel, ShadowField, build_shadow_field,
    cast_shadow, fraction_sun, read_model, solar_angles,
)
from app.shade.scoring import RouteEdge, score_route

X, Y = PROJECTION.transform(-118.4452, 34.0689)


def metric_box(x1, y1, x2, y2):
    return box(X + x1, Y + y1, X + x2, Y + y2)


def edge(points=((0, 0), (100, 0)), duration=100):
    return RouteEdge(tuple(INVERSE_PROJECTION.transform(X + x, Y + y) for x, y in points), duration)


def field(shadows=None, coverage=None, status="daylight"):
    return ShadowField(shadows if shadows is not None else Polygon(), coverage, status,
                       data_as_of="synthetic fixture", source="unit test")


def assert_conserved(result):
    assert sum(s.distance_m for s in result.segments) == pytest.approx(result.distance_m)
    assert sum(s.duration_s for s in result.segments) == pytest.approx(result.duration_s)
    assert result.shade_seconds + result.known_sun_seconds + result.unknown_seconds + result.no_direct_sun_seconds == pytest.approx(result.duration_s)
    assert 0 <= result.sun_seconds_min <= result.sun_seconds_max <= result.duration_s + 1e-7
    assert 0 <= result.known_fraction <= 1
    for a, b in zip(result.segments, result.segments[1:]):
        assert a.geometry["coordinates"][-1] == pytest.approx(b.geometry["coordinates"][0])
    json.dumps(result.to_dict(), allow_nan=False)


@pytest.mark.parametrize("azimuth,bounds", [
    (90, (-10, 0, 10, 10)), (180, (0, 0, 10, 20)),
    (270, (0, 0, 20, 10)), (0, (0, -10, 10, 10)),
])
def test_shadow_direction_and_reach(azimuth, bounds):
    shadow = cast_shadow(box(0, 0, 10, 10), 10, 45, azimuth)
    assert shadow.bounds == pytest.approx(bounds)
    assert shadow.area == pytest.approx(200)


def test_concave_building_is_not_filled_to_convex_hull():
    footprint = Polygon([(0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10)])
    shadow = cast_shadow(footprint, 1, 45, 90)
    assert not shadow.covers(Point(5, 5))
    assert shadow.covers(Point(-.5, 5))
    assert shadow.area < shadow.convex_hull.area


def test_courtyard_and_multipolygon_preserved():
    courtyard = Polygon(box(0, 0, 20, 20).exterior.coords,
                        [box(5, 5, 15, 15).exterior.coords])
    shadow = cast_shadow(courtyard, 1, 45, 90)
    assert not shadow.covers(Point(10, 10))
    assert shadow.covers(Point(14.5, 10))
    multi = cast_shadow(MultiPolygon([box(0, 0, 2, 2), box(10, 0, 12, 2)]), 1, 45, 90)
    assert not multi.covers(Point(5, 1))


def test_long_shadow_not_silently_truncated():
    shadow = cast_shadow(box(0, 0, 1, 1), 100, 3, 90)
    assert shadow.bounds[0] == pytest.approx(-100 / tan(radians(3)))


@pytest.mark.parametrize("height,elevation,azimuth", [(0, 45, 90), (10, 2, 90), (10, -1, 90), (10, 91, 90), (10, 45, float("nan"))])
def test_invalid_shadow_parameters_rejected(height, elevation, azimuth):
    with pytest.raises(ValueError):
        cast_shadow(box(0, 0, 1, 1), height, elevation, azimuth)


def test_exact_fraction_and_ordered_map_segments():
    result = score_route([edge()], field(metric_box(-1, -10, 40, 10), metric_box(-10, -10, 110, 10)))
    assert result.distance_m == pytest.approx(100, abs=1e-6)
    assert result.shade_seconds == pytest.approx(40, abs=1e-6)
    assert result.sun_seconds == pytest.approx(60, abs=1e-6)
    assert result.shade_fraction == pytest.approx(.4, abs=1e-7)
    assert [s.shade_state for s in result.segments] == ["shade", "sun"]
    assert_conserved(result)


def test_overlap_does_not_double_count_shade():
    shadows = unary_union([metric_box(-1, -10, 50, 10), metric_box(25, -10, 75, 10)])
    result = score_route([edge()], field(shadows, metric_box(-10, -10, 110, 10)))
    assert result.shade_seconds == pytest.approx(75, abs=1e-6)
    assert_conserved(result)


def test_partial_coverage_does_not_turn_unknown_into_sun():
    result = score_route([edge()], field(metric_box(-1, -10, 40, 10), metric_box(-10, -10, 70, 10)))
    assert result.shade_seconds == pytest.approx(40, abs=1e-6)
    assert result.known_sun_seconds == pytest.approx(30, abs=1e-6)
    assert result.unknown_seconds == pytest.approx(30, abs=1e-6)
    assert result.sun_seconds is None and result.shade_fraction is None
    assert result.sun_seconds_min == pytest.approx(30, abs=1e-6)
    assert result.sun_seconds_max == pytest.approx(60, abs=1e-6)
    assert [s.shade_state for s in result.segments] == ["shade", "sun", "unknown"]
    assert_conserved(result)


@pytest.mark.parametrize("status", ["unavailable", "low_sun"])
def test_missing_or_low_sun_is_unknown_even_with_stale_geometry(status):
    result = score_route([edge()], field(metric_box(-10, -10, 110, 10), status=status))
    assert result.sun_seconds is None
    assert result.unknown_seconds == pytest.approx(100)
    assert result.known_fraction == 0
    assert_conserved(result)


def test_no_verified_coverage_allows_shade_but_not_sun():
    result = score_route([edge()], field(metric_box(-1, -10, 40, 10)))
    assert result.unknown_seconds == pytest.approx(60, abs=1e-6)
    assert result.known_sun_seconds == 0
    assert_conserved(result)


def test_night_has_zero_direct_sun_but_is_not_daytime_shade():
    result = score_route([edge()], field(status="night"))
    assert result.sun_seconds == 0 and result.unknown_seconds == 0
    assert result.shade_seconds == 0 and result.shade_fraction is None
    assert result.no_direct_sun_seconds == pytest.approx(100)
    assert result.segments[0].shade_state == "no_direct_sun"
    assert_conserved(result)


def test_real_solar_night_without_building_data():
    actual = build_shadow_field(None, datetime.fromisoformat("2026-07-15T23:00:00-07:00"))
    assert actual.status == "night"
    assert score_route([edge()], actual).sun_seconds == 0


def test_retraced_edge_and_reverse_route_count_every_traversal():
    shadows = metric_box(-1, -10, 40, 10)
    coverage = metric_box(-10, -10, 110, 10)
    result = score_route([edge(((0, 0), (100, 0), (0, 0)), 200)], field(shadows, coverage))
    assert result.shade_seconds == pytest.approx(80, abs=1e-6)
    assert result.sun_seconds == pytest.approx(120, abs=1e-6)
    assert [s.shade_state for s in result.segments] == ["shade", "sun", "shade"]
    assert fraction_sun(shadows, list(edge(((0, 0), (100, 0), (0, 0))).coordinates)) == pytest.approx(.6, abs=1e-7)
    reverse = score_route([edge(((100, 0), (0, 0)))], field(shadows, coverage))
    assert reverse.sun_seconds == pytest.approx(60, abs=1e-6)
    assert_conserved(result)


def test_distance_fraction_and_time_exposure_handle_different_edge_speeds():
    result = score_route([edge(((0, 0), (50, 0)), 100), edge(((50, 0), (100, 0)), 25)],
                         field(metric_box(-1, -10, 49.99999, 10), metric_box(-10, -10, 110, 10)))
    assert result.shade_fraction == pytest.approx(.5, abs=1e-6)
    assert result.sun_seconds == pytest.approx(25, abs=1e-4)
    assert_conserved(result)


def test_narrow_shade_strip_not_missed_by_fixed_sampling():
    shadows = metric_box(1, -10, 2, 10)
    result = score_route([edge()], field(shadows, metric_box(-10, -10, 110, 10)))
    assert result.shade_seconds == pytest.approx(1, abs=1e-6)
    assert fraction_sun(shadows, list(edge().coordinates)) == pytest.approx(.99, abs=1e-7)


def test_tangency_is_zero_length_not_shaded_road():
    # Construct boundary relative to projected road to avoid round-trip EPS noise.
    road = transform(PROJECTION.transform, LineString(edge().coordinates))
    x, y = road.interpolate(50).coords[0]
    triangle = Polygon([(x, y), (x - 10, y + 10), (x + 10, y + 10)])
    result = score_route([edge()], field(triangle, metric_box(-10, -10, 110, 10)))
    assert result.shade_seconds == pytest.approx(0, abs=1e-6)
    assert_conserved(result)


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf"), True])
def test_invalid_duration_rejected(duration):
    with pytest.raises(ValueError):
        score_route([edge(duration=duration)], field())


def test_empty_degenerate_disconnected_and_wrong_crs_rejected():
    for edges in ([], [edge(((0, 0), (0, 0)))], [edge(), edge(((200, 0), (250, 0)))],
                  [RouteEdge(((34.06, -118.44), (34.07, -118.44)), 100)]):
        with pytest.raises(ValueError):
            score_route(edges, field())


def test_solar_timezone_equivalence_and_dst():
    for local in (datetime(2026, 7, 15, 14, tzinfo=ZoneInfo("America/Los_Angeles")),
                  datetime(2026, 11, 1, 1, 30, fold=0, tzinfo=ZoneInfo("America/Los_Angeles")),
                  datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=ZoneInfo("America/Los_Angeles"))):
        assert solar_angles(local) == pytest.approx(solar_angles(local.astimezone(timezone.utc)))
    with pytest.raises(ValueError, match="timezone"):
        build_shadow_field(None, datetime(2026, 7, 15, 14))


@pytest.mark.parametrize("elevation,status", [(-5, "night"), (0, "night"), (1, "low_sun"), (2, "low_sun"), (45, "unavailable")])
def test_shadow_field_sun_boundaries(monkeypatch, elevation, status):
    monkeypatch.setattr(shade_model, "solar_angles", lambda when: (elevation, 90))
    assert build_shadow_field(None, datetime.now(timezone.utc)).status == status


def test_daylight_field_requires_bounded_verified_coverage(monkeypatch):
    monkeypatch.setattr(shade_model, "solar_angles", lambda when: (45, 90))
    model = ShadeModel(((metric_box(10, 0, 20, 10), 10),), "fixture", True,
                       metric_box(-10, -10, 110, 10), "unit test")
    result = build_shadow_field(model, datetime.now(timezone.utc))
    assert result.status == "daylight" and result.shadows.area > 0
    assert result.coverage_geometry.equals(model.coverage_geometry)
    assert build_shadow_field(ShadeModel(model.shapes, None, True), datetime.now(timezone.utc)).coverage_geometry is None


def write_model(tmp_path, height=10, *, complete=True, geometry=None):
    polygon = mapping(transform(INVERSE_PROJECTION.transform, metric_box(0, 0, 10, 10)))
    raw = {"type": "FeatureCollection", "metadata": {
        "coverage_complete_verified": complete, "coverage_geometry": polygon,
        "source": "synthetic fixture", "data_as_of": "test only"},
        "features": [{"type": "Feature", "geometry": geometry or polygon,
                      "properties": {"height_m": height}}]}
    path = tmp_path / "buildings.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.mark.parametrize("height", [None, True, -1, 999, "10", float("nan")])
def test_bad_height_not_fabricated_or_complete(tmp_path, height):
    model = read_model(write_model(tmp_path, height))
    assert model.shapes == ()
    assert model.coverage_complete_verified is False


def test_loader_provenance_and_coordinate_validation(tmp_path):
    model = read_model(write_model(tmp_path))
    assert len(model.shapes) == 1 and model.coverage_complete_verified
    assert model.source == "synthetic fixture" and model.data_as_of == "test only"
    for bad_geometry in (mapping(box(0, 0, 10, 10)), mapping(Point(-118.44, 34.06))):
        with pytest.raises(ValueError):
            read_model(write_model(tmp_path, geometry=bad_geometry))


def test_cli_real_solar_pipeline_and_missing_data(tmp_path, monkeypatch, capsys):
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    import sys

    path = Path(__file__).resolve().parents[2] / "scripts" / "score_route_shade.py"
    spec = spec_from_file_location("score_route_shade_cli", path)
    cli = module_from_spec(spec)
    spec.loader.exec_module(cli)
    route_path = tmp_path / "route.json"
    route_path.write_text(json.dumps({"type": "Feature", "geometry": {
        "type": "LineString", "coordinates": edge().coordinates},
        "properties": {"duration_s": 100}}), encoding="utf-8")
    buildings_path = write_model(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(path), "--route", str(route_path),
        "--buildings", str(buildings_path), "--departure", "2026-07-15T14:00:00-07:00"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["model_status"] == "daylight"
    assert result["source"] == "synthetic fixture"
    assert sum(s["duration_s"] for s in result["segments"]) == pytest.approx(100)
    monkeypatch.setattr(sys, "argv", [str(path), "--route", str(route_path),
        "--departure", "2026-07-15T14:00:00-07:00"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["sun_seconds"] is None and result["unknown_seconds"] == 100


def test_cli_rejects_bad_route_and_naive_time(tmp_path, monkeypatch, capsys):
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path
    import sys

    path = Path(__file__).resolve().parents[2] / "scripts" / "score_route_shade.py"
    spec = spec_from_file_location("score_route_shade_cli_invalid", path)
    cli = module_from_spec(spec)
    spec.loader.exec_module(cli)
    route = tmp_path / "bad-route.json"
    route.write_text(json.dumps({"type": "LineString", "coordinates": edge().coordinates}))
    with pytest.raises(ValueError, match="Feature"):
        cli.read_edges(route)
    route.write_text(json.dumps({"type": "Feature", "geometry": {
        "type": "LineString", "coordinates": edge().coordinates},
        "properties": {"duration_s": 100}}))
    monkeypatch.setattr(sys, "argv", [str(path), "--route", str(route),
                                     "--departure", "2026-07-15T14:00:00"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "timezone" in capsys.readouterr().err
