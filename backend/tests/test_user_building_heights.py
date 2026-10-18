from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def updater():
    path = Path(__file__).resolve().parents[2] / "scripts" / "apply_user_building_heights.py"
    spec = spec_from_file_location("apply_user_building_heights", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_user_estimates_are_labeled_and_unnamed_features_are_excluded():
    module = updater()
    features = []
    for way_id in (*module.HEIGHTS, *module.IGNORED):
        features.append({"type": "Feature", "geometry": None, "properties": {
            "osm_id": f"('way', {way_id})", "height_m": None,
            "height_exclusion_reason": "unknown"}})
    result, report = module.apply({"type": "FeatureCollection", "metadata": {},
                                   "features": features})
    assert report == {"features": 16, "applied": 16, "ignored": 3, "unknown_heights": 0}
    assert {int(feature["properties"]["osm_id"].split(", ")[1][:-1])
            for feature in result["features"]} == set(module.HEIGHTS)
    assert all(feature["properties"]["height_method"] == "user_supplied_estimate"
               and feature["properties"]["field_verified"] is False
               and "height_exclusion_reason" not in feature["properties"]
               for feature in result["features"])
    assert result["metadata"]["coverage_complete_verified"] is False
    assert result["metadata"]["ignored_unnamed_osm_ways"] == sorted(module.IGNORED)
