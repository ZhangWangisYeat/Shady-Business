"""Synthetic OSM bundle tests; no network or real campus source assets."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from app.shade.model import read_model

spec = spec_from_file_location("import_osm_buildings", Path(__file__).resolve().parents[2] / "scripts" / "import_osm_buildings.py")
importer = module_from_spec(spec)
spec.loader.exec_module(importer)


def bundle():
    geometry = {"type": "Polygon", "coordinates": [[[-118.445, 34.068],
        [-118.4449, 34.068], [-118.4449, 34.0681], [-118.445, 34.0681], [-118.445, 34.068]]]}
    buildings = [{"type": "Feature", "geometry": deepcopy(geometry),
                  "properties": {"height_m": height, "height_source": method, "osm_id": str(index)}}
                 for index, (height, method) in enumerate([
                     (20, "OSM height tag (unverified)"),
                     (12, "default assumed 12m"),
                     (9.6, "OSM levels × assumed 3.2m")])]
    return {"metadata": {"mode": "osm", "license": "ODbL 1.0", "fetched_at": "2026-10-17"},
            "buildings": buildings, "trees": [{"properties": {"source": "assumed 4m crown"}}]}


def test_preserves_footprints_without_promoting_assumed_heights():
    original = bundle()
    before = deepcopy(original)
    result, report = importer.prepare_buildings(original, "sha256:synthetic")
    assert original == before
    assert [f["properties"]["height_m"] for f in result["features"]] == [20, None, None]
    assert report["usable_osm_height_tags"] == 1 and report["unknown_heights"] == 2
    assert report["excluded_tree_or_wood_features"] == 1
    assert result["metadata"]["source_file_checksum"] == "sha256:synthetic"
    assert result["metadata"]["data_as_of"] is None
    assert result["metadata"]["retrieved_at"] == "2026-10-17"
    assert result["metadata"]["coverage_complete_verified"] is False


def test_imported_file_loads_with_unknown_coverage(tmp_path):
    result, _ = importer.prepare_buildings(bundle(), "sha256:synthetic")
    path = tmp_path / "buildings.geojson"
    path.write_text(json.dumps(result), encoding="utf-8")
    model = read_model(path)
    assert len(model.shapes) == 1 and model.coverage_complete_verified is False


@pytest.mark.parametrize("key,value", [("mode", "demo"), ("license", "unknown")])
def test_no_demo_or_unattributed_source(key, value):
    raw = bundle()
    raw["metadata"][key] = value
    with pytest.raises(ValueError, match="provenance"):
        importer.prepare_buildings(raw, "sha256:synthetic")


@pytest.mark.parametrize("height", [True, float("nan"), 999, "20"])
def test_invalid_tag_height_remains_unknown(height):
    raw = bundle()
    raw["buildings"][0]["properties"]["height_m"] = height
    result, _ = importer.prepare_buildings(raw, "sha256:synthetic")
    assert result["features"][0]["properties"]["height_m"] is None


def test_bad_crs_rejected_before_export():
    raw = bundle()
    raw["buildings"][0]["geometry"]["coordinates"] = [[[0, 0], [1, 0], [1, 1], [0, 0]]]
    with pytest.raises(ValueError, match="WGS84"):
        importer.prepare_buildings(raw, "sha256:synthetic")
