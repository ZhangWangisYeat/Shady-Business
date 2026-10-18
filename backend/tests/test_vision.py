"""Offline checks for the vision gap-filling pipeline; no network, no API keys."""
import json

import pytest
from shapely.geometry import box

from app.shade.trees import read_tree_model
from app.vision.compare import (aerial_candidates, candidate_feature, match_inventory, merge_duplicates,
                                merged_tree_file, street_candidates)
from app.vision.gaps import find_gap_sites, sample_route
from app.vision.gemini import Budget, QuotaReached, build_request, parse_response
from app.vision.geo import bbox_around, bearing_of, grid_to_lonlat, meters_between, offset

COVERED = box(-118.448, 34.0675, -118.438, 34.0755)
INSIDE = (-118.4430, 34.0710)
OLYMPIC = (-118.4536, 34.0724)  # on the hill, outside the inventory rectangle


def gemini(payload: dict) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 300}}


def test_aerial_grid_maps_to_the_tile_corners_and_middle():
    tile = bbox_around(*OLYMPIC, 140)
    west, south, east, north = tile
    assert grid_to_lonlat(0, 0, tile) == pytest.approx((west, north))
    assert grid_to_lonlat(1000, 1000, tile) == pytest.approx((east, south))
    assert meters_between(grid_to_lonlat(500, 500, tile), OLYMPIC) < 0.5


def test_photo_columns_turn_into_compass_bearings():
    assert bearing_of(500, 90, 70, panorama=False) == pytest.approx(90)
    assert bearing_of(1000, 90, 70, panorama=False) == pytest.approx(125)
    # a panorama spans the whole circle with the heading in the middle
    assert bearing_of(0, 90, 0, panorama=True) == pytest.approx(270)


def test_places_outside_coverage_are_gaps_and_neighbours_share_a_site():
    places = [{"id": "olympic-hall", "name": "Olympic Hall", "coordinate": OLYMPIC},
              {"id": "next-door", "name": "Next Door", "coordinate": offset(*OLYMPIC, 0, 50)},
              {"id": "royce-hall", "name": "Royce Hall", "coordinate": INSIDE},
              {"id": "far-court", "name": "Far Court", "coordinate": (-118.4520, 34.0700)}]
    trees = [offset(*INSIDE, angle, 20) for angle in range(0, 360, 60)]
    sites = find_gap_sites(places, trees, COVERED, focus=["Olympic"])
    assert [s.name for s in sites] == ["Olympic Hall", "Far Court"]
    assert sites[0].place_ids == ["olympic-hall", "next-door"]
    assert sites[0].reason == "outside_inventory"


def test_a_covered_place_with_almost_no_trees_is_a_sparse_gap():
    sites = find_gap_sites([{"id": "field", "name": "Intramural Field", "coordinate": INSIDE}], [], COVERED)
    assert sites[0].reason == "sparse_inventory"


def test_route_samples_only_the_uncovered_stretch():
    line = [(-118.4400, 34.0700), (-118.4600, 34.0700)]  # starts inside, runs west off the rectangle
    sites = sample_route(line, COVERED, every_m=200)
    assert sites and all(not COVERED.contains_properly(box(*s.coordinate, *s.coordinate).centroid) for s in sites)


def test_parsing_clamps_numbers_and_drops_broken_shapes():
    parsed = parse_response(gemini({
        "trees": [{"kind": "tree", "outline": [{"x": -5, "y": 10}, {"x": 40, "y": 10}, {"x": 40, "y": 1200}], "height_m": 9, "confidence": 1.4},
                  {"kind": "tree", "outline": [{"x": 1, "y": 1}], "height_m": 5, "confidence": 0.9}],
        "ground": [{"state": "shade", "outline": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]},
                   {"state": "dusk", "outline": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]}],
        "buildings": []}), "aerial")
    assert len(parsed["trees"]) == 1
    assert parsed["trees"][0]["outline"][0] == (0, 10) and parsed["trees"][0]["outline"][2] == (40, 1000)
    assert parsed["trees"][0]["confidence"] == 1
    assert [g["state"] for g in parsed["ground"]] == ["shade"]
    assert parsed["tokens"]["prompt"] == 900


def test_street_trees_past_60_m_are_dropped():
    parsed = parse_response(gemini({"trees": [
        {"kind": "tree", "box": [100, 100, 300, 600], "trunk_x": 200, "distance_m": 12, "height_m": 8, "crown_width_m": 6, "confidence": 0.8},
        {"kind": "tree", "box": [400, 100, 500, 300], "trunk_x": None, "distance_m": 90, "height_m": 8, "crown_width_m": 6, "confidence": 0.8}],
        "ground": {"shade_share": 0.4, "sun_share": 0.6, "camera_in_shade": False}, "buildings": []}), "street")
    assert len(parsed["trees"]) == 1 and parsed["ground"]["shade_share"] == 0.4


def test_bad_json_is_an_error_not_an_empty_map():
    with pytest.raises(ValueError):
        parse_response({"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}, "aerial")


def test_the_request_asks_for_strict_json_and_keeps_the_key_out_of_the_url():
    photo = {"kind": "aerial", "site_name": "Olympic Hall", "coordinate": OLYMPIC, "size_m": 140}
    body = build_request(b"\xff\xd8", "image/jpeg", photo)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["temperature"] == 0
    assert "Olympic Hall" in body["contents"][0]["parts"][0]["text"]
    sent = {}
    Budget(1, 0).call("secret-key", "gemini-test", body, post=lambda url, b, headers: sent.update(url=url, headers=headers) or {})
    assert "secret-key" not in sent["url"] and sent["headers"]["x-goog-api-key"] == "secret-key"


def test_the_budget_spaces_calls_and_stops_at_the_cap_or_a_429():
    slept, now = [], [0.0]
    budget = Budget(2, 7, sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)), clock=lambda: now[0])
    budget.call("k", "m", {}, post=lambda *a: {})
    budget.call("k", "m", {}, post=lambda *a: {})
    assert slept == [7]
    with pytest.raises(QuotaReached):
        budget.call("k", "m", {}, post=lambda *a: {})

    def busy(*args):
        raise QuotaReached("429")
    with pytest.raises(QuotaReached):
        Budget(5, 0).call("k", "m", {}, post=busy)


def square(center, side_m):
    """A crown outline on the 0-1000 grid of a 140 m tile centered on center."""
    half = side_m / 140 * 1000 / 2
    return [(500 - half, 500 - half), (500 + half, 500 - half), (500 + half, 500 + half), (500 - half, 500 + half)]


def aerial_photo():
    return {"id": "naip-olympic", "kind": "aerial", "bbox": list(bbox_around(*OLYMPIC, 140)), "coordinate": list(OLYMPIC)}


def test_an_aerial_crown_becomes_a_tree_with_an_equal_area_radius():
    detections = {"trees": [{"kind": "tree", "outline": square(OLYMPIC, 10), "height_m": 9.0, "confidence": 0.8}], "ground": []}
    [cand] = aerial_candidates(detections, aerial_photo())
    assert meters_between((cand.lon, cand.lat), OLYMPIC) < 0.5
    assert cand.crown_radius_m == pytest.approx((100 / 3.14159) ** 0.5, rel=0.03)


def test_a_street_tree_is_placed_along_the_camera_bearing():
    photo = {"id": "mly-1", "kind": "street", "coordinate": list(OLYMPIC), "heading": 0, "panorama": False, "focal": None}
    detections = {"trees": [{"kind": "tree", "box": [450, 0, 550, 600], "trunk_x": 500, "distance_m": 20,
                             "height_m": 10, "crown_width_m": 8, "confidence": 0.9}], "ground": {}}
    [cand] = street_candidates(detections, photo)
    assert meters_between((cand.lon, cand.lat), offset(*OLYMPIC, 0, 20)) < 0.5
    assert cand.crown_radius_m == 4 and cand.uncertainty_m == 5


def test_one_tree_in_two_photos_is_one_candidate_at_the_better_position():
    aerial = aerial_candidates({"trees": [{"kind": "tree", "outline": square(OLYMPIC, 8), "height_m": None, "confidence": 0.7}]}, aerial_photo())
    photo = {"id": "mly-2", "kind": "street", "coordinate": list(offset(*OLYMPIC, 180, 15)), "heading": 0, "panorama": False}
    street = street_candidates({"trees": [{"kind": "tree", "box": [450, 0, 550, 600], "trunk_x": 500, "distance_m": 16,
                                           "height_m": 11, "crown_width_m": 7, "confidence": 0.9}]}, photo)
    [merged] = merge_duplicates(aerial + street)
    assert merged.sources == ["mly-2", "naip-olympic"]
    assert meters_between((merged.lon, merged.lat), OLYMPIC) < 0.5
    assert merged.height_m == 11  # the aerial didn't know the height, the street photo did


def inventory_tree(where, tree_id="inv-1"):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": list(where)},
            "properties": {"tree_id": tree_id, "globalid": tree_id, "status": "tree", "height_m": 12.0, "crown_radius_m": 4.0}}


def test_only_confident_new_single_trees_are_accepted():
    photo = aerial_photo()
    found = aerial_candidates({"trees": [
        {"kind": "tree", "outline": square(OLYMPIC, 8), "height_m": 9.0, "confidence": 0.8},
        {"kind": "shrub", "outline": square(offset(*OLYMPIC, 90, 30), 3), "height_m": 1.5, "confidence": 0.9},
    ]}, photo)
    known = aerial_candidates({"trees": [{"kind": "tree", "outline": square(OLYMPIC, 8), "height_m": 13.0, "confidence": 0.9}]},
                              {**photo, "bbox": list(bbox_around(*offset(*OLYMPIC, 90, 60), 140))})
    candidates = found + known
    match_inventory(candidates, [inventory_tree(offset(*OLYMPIC, 90, 60))])
    states = [candidate_feature(c, 0.6)["properties"]["status"] for c in candidates]
    # the new tree is in, the shrub waits for review, the known tree stays the inventory's
    assert states == ["tree", "vision_review", "vision_review"]
    assert candidates[2].matched_inventory == "inv-1"


def test_the_merged_file_loads_in_the_shade_model_and_keeps_the_inventory(tmp_path):
    inventory = {"type": "FeatureCollection", "metadata": {
        "height_unit": "m", "crown_radius_unit": "m", "coordinate_reference_system": "EPSG:4326",
        "coverage_complete_verified": True, "coverage_geometry": json.loads(json.dumps(COVERED.__geo_interface__))},
        "features": [inventory_tree(INSIDE)]}
    [cand] = aerial_candidates({"trees": [{"kind": "tree", "outline": square(OLYMPIC, 8), "height_m": 9.0, "confidence": 0.8}]}, aerial_photo())
    review = aerial_candidates({"trees": [{"kind": "shrub", "outline": square(OLYMPIC, 3), "height_m": 1.0, "confidence": 0.9}]}, aerial_photo())[0]
    candidates = {"features": [candidate_feature(cand, 0.6), candidate_feature(review, 0.6)]}
    merged = merged_tree_file(inventory, candidates, [aerial_photo()], extend_coverage=True)
    path = tmp_path / "trees.geojson"
    path.write_text(json.dumps(merged), encoding="utf-8")
    dataset = read_tree_model(path)
    assert len(dataset.trees) == 2  # inventory tree plus the accepted vision tree, not the shrub
    assert dataset.coverage_complete_verified  # no review records leak in as "unmodeled"
    assert merged["metadata"]["vision_supplement"]["independently_verified"] is False
    assert dataset.coverage_geometry.area > 0
