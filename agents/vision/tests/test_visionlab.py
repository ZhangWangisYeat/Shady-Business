"""Offline checks for VisionLab's building blocks: no imagery service, no agent network."""
import sys
from math import pi
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visionlab.allometry import HeightModel  # noqa: E402
from visionlab.compare import mask_scores, match_points  # noqa: E402
from visionlab.imagery import Tile, bbox_around  # noqa: E402
from visionlab.labels import geometries, rasterize  # noqa: E402
from visionlab.models import shadow, vegetation, water  # noqa: E402
from visionlab.requests import parse  # noqa: E402
from visionlab.tasks import run  # noqa: E402
from visionlab.vectorize import crowns, polygons  # noqa: E402

CENTER = (-118.4536, 34.0724)


def blank_tile(size_m=60, rgbn=(120, 120, 120, 60)) -> Tile:
    bbox = bbox_around(*CENTER, size_m)
    px = round(size_m / 0.6)
    pixels = np.zeros((px, px, 4), np.uint8) + np.array(rgbn, np.uint8)
    return Tile(pixels, np.ones((px, px), bool), bbox, "test", "2022-05-11")


def point(lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def test_pixels_and_coordinates_round_trip():
    tile = blank_tile()
    lon, lat = tile.pixel_to_lonlat(10, 40)
    assert tile.lonlat_to_pixel(lon, lat) == pytest.approx((10, 40))
    assert tile.meters_per_pixel == pytest.approx(0.6, rel=0.01)


def test_a_crown_label_covers_about_pi_r_squared():
    tile = blank_tile()
    mask = rasterize(tile, geometries([point(*CENTER, crown_radius_m=5)], "crown_radius_m"))
    assert mask.sum() * 0.36 == pytest.approx(pi * 25, rel=0.1)


def test_touching_crowns_are_split_into_separate_trees():
    tile = blank_tile(80)
    left, right = (CENTER[0] - 6 / 92_000, CENTER[1]), (CENTER[0] + 6 / 92_000, CENTER[1])
    mask = rasterize(tile, geometries([point(*left, r=5), point(*right, r=5)], "r"))
    found = crowns(mask, tile)
    assert len(found) == 2
    assert all(c["crown_radius_m"] == pytest.approx(5, rel=0.25) for c in found)


def test_a_mask_becomes_a_polygon_of_the_right_size():
    tile = blank_tile()
    mask = rasterize(tile, geometries([point(*CENTER, r=8)], "r"))
    [poly] = polygons(mask, tile)
    area = poly.area * 111_320 ** 2 * np.cos(np.radians(CENTER[1]))
    assert area == pytest.approx(pi * 64, rel=0.15)


def test_each_reference_object_is_matched_once():
    detections = [{"lon": CENTER[0], "lat": CENTER[1]}, {"lon": CENTER[0] + 1e-6, "lat": CENTER[1]}]
    result = match_points(detections, [point(*CENTER)])
    assert len(result["matches"]) == 1 and len(result["new"]) == 1 and result["recall"] == 1


def test_mask_scores():
    a = np.zeros((4, 4), bool); a[:2] = True
    b = np.zeros((4, 4), bool); b[1:3] = True
    scores = mask_scores(a, b, np.ones((4, 4), bool))
    assert scores["iou"] == pytest.approx(4 / 12)


def test_height_model_recovers_a_power_law():
    radii = np.linspace(1, 12, 200)
    model = HeightModel.fit(list(3 * radii ** 0.7), list(radii))
    assert model.slope == pytest.approx(0.7, abs=0.01)
    assert model.predict(5) == pytest.approx(3 * 5 ** 0.7, rel=0.01)


def test_builtin_models_on_pure_surfaces():
    leaves = blank_tile(rgbn=(40, 90, 40, 200))   # dark red, bright near infrared
    pond = blank_tile(rgbn=(30, 80, 110, 10))      # near infrared absorbed
    assert vegetation(leaves).all() and not vegetation(pond).any()
    assert water(pond).all() and not water(leaves).any()
    half = blank_tile(rgbn=(200, 200, 200, 150))
    half.pixels[:, :40] = (40, 45, 60, 30)         # a dark, bluish strip: shadow
    assert shadow(half)[:, :40].mean() > 0.9 and shadow(half)[:, 60:].mean() < 0.1


@pytest.mark.parametrize("text, action, target, places", [
    ("Find tree canopy at Olympic Hall and compare with the UCLA trees inventory", "analyze", "tree_canopy", ["Olympic Hall"]),
    ("Map the trees along the walk from Olympic Hall to Royce Hall", "path", "tree_canopy", ["Olympic Hall", "Royce Hall"]),
    ("Classify the land cover around Royce Hall", "analyze", "land_cover", ["Royce Hall"]),
    ("Where is the water near 34.0700, -118.4420 within 200 m?", "analyze", "water", ["34.07000, -118.44200"]),
    ("what can you do?", "help", None, []),
])
def test_requests_are_understood(text, action, target, places):
    request = parse(text)
    assert request.action == action and request.target == target and [p[0] for p in request.places] == places


def test_no_place_gets_a_helpful_answer_not_a_crash():
    request = parse("find buildings")
    request.places = []
    assert "couldn't tell where" in run(request)
