#!/usr/bin/env python3
"""Export a test-only route field checklist without promoting shade coverage."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shapely.geometry import LineString, box, mapping, shape
from shapely.ops import transform, unary_union

from audit_shade_coverage import route_candidate_envelopes, shadow_input_extent
from app.places.catalog import find_place
from app.routing import service
from app.routing.graph import load_graph
from app.settings import GRAPH_FILE
from app.shade.model import INVERSE_PROJECTION, PROJECTION, ShadeModel, _project_polygon, load_model
from validate_field_audit import structure_sha256


def file_identity(path: Path) -> dict:
    return {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build_audit_geojson(response, *, origin_id: str, destination_id: str,
                        when: datetime, temperature_c: float,
                        building_reach_m: float, tree_reach_m: float,
                        candidate_bbox: tuple[float, float, float, float] | None = None) -> dict:
    features = []
    projected_routes = []
    route_summaries = []
    for route in response.routes:
        coordinates = route.geometry.coordinates
        projected_routes.append(transform(PROJECTION.transform, LineString(coordinates)))
        route_summaries.append({
            "mode": route.mode, "duration_s": route.duration_s,
            "distance_m": route.distance_m, "sun_seconds": route.sun_seconds,
            "same_as": route.same_as,
        })
        features.append({
            "type": "Feature", "geometry": route.geometry.model_dump(),
            "properties": {"feature_kind": "candidate_route", "mode": route.mode,
                           "duration_s": route.duration_s, "distance_m": route.distance_m,
                           "sun_seconds": route.sun_seconds, "same_as": route.same_as,
                           "assumed_coverage_only": True},
        })
        projected_segments = []
        for index, segment in enumerate(route.segments, start=1):
            line = transform(PROJECTION.transform, LineString(segment.geometry.coordinates))
            if line.length <= 0:
                continue
            projected_segments.append((segment, line))
            features.append({
                "type": "Feature", "geometry": segment.geometry.model_dump(),
                "properties": {
                    "feature_kind": "modeled_segment", "segment_id": f"{route.mode}-{index:03}",
                    "mode": route.mode, "expected_state": segment.shade_state,
                    "expected_state_is_model_only": True,
                    "segment_duration_s": segment.duration_s,
                },
            })
        route_line = projected_routes[-1]
        checks = []
        for state in sorted({segment.shade_state for segment, _ in projected_segments}):
            segment, line = max(
                (item for item in projected_segments if item[0].shade_state == state),
                key=lambda item: item[1].length)
            point = line.interpolate(.5, normalized=True)
            checks.append((route_line.project(point) / route_line.length, point, segment))
        for fraction in (.1, .3, .5, .7, .9):
            if len(checks) >= 5:
                break
            if any(abs(existing[0] - fraction) < .08 for existing in checks):
                continue
            point = route_line.interpolate(fraction, normalized=True)
            segment, _ = min(projected_segments, key=lambda item: item[1].distance(point))
            checks.append((fraction, point, segment))
        for check_index, (fraction, projected_point, segment) in enumerate(
                sorted(checks, key=lambda item: item[0]), start=1):
            point = transform(INVERSE_PROJECTION.transform, projected_point)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
                "properties": {
                    "feature_kind": "field_check", "audit_id": f"{route.mode}-{check_index:02}",
                    "mode": route.mode, "route_progress": fraction,
                    "expected_state": segment.shade_state,
                    "expected_state_is_model_only": True,
                    "verify_buildings_within_m": round(building_reach_m, 2),
                    "verify_trees_within_m": round(tree_reach_m, 2),
                    "actual_state": None, "missing_obstruction": None,
                    "photo_reference": None, "notes": None,
                },
            })

    inspection_buffer_m = max(building_reach_m, tree_reach_m)
    candidate_scope = (
        transform(PROJECTION.transform, box(*candidate_bbox))
        if candidate_bbox is not None
        else unary_union(projected_routes)
    )
    inspection_zone = transform(
        INVERSE_PROJECTION.transform,
        candidate_scope.buffer(inspection_buffer_m),
    )
    features.append({
        "type": "Feature", "geometry": mapping(inspection_zone),
        "properties": {"feature_kind": "inspection_zone",
                       "scope": ("all_maximum_shade_eligible_edges_bbox"
                                 if candidate_bbox is not None else "returned_routes"),
                       "buffer_m": round(inspection_buffer_m, 2),
                       "coverage_complete_verified": False},
    })
    return {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": 1,
            "purpose": "On-site completeness and modeled-state checklist",
            "origin_place_id": origin_id, "destination_place_id": destination_id,
            "departure_time": when.isoformat(), "temperature_c": temperature_c,
            "assumed_coverage_only": True, "coverage_complete_verified": False,
            "not_runtime_shade_input": True,
            "review": {
                "review_reference": None,
                "reviewed_at": None,
                "review_method": None,
                "inspection_zone_complete": None,
                "outside_shadow_casters_checked": None,
                "source_reuse_authorized": None,
            },
            "instructions": [
                "At each field_check point, record actual sun/shade at the stated local time.",
                "Record any building or tree inside the stated radii that is missing from the model.",
                "Do not promote coverage until every point and the inspection zone are reviewed.",
            ],
            "routes": route_summaries,
        },
        "features": features,
    }


def add_obstruction_checks(result: dict, buildings_raw: dict, trees_raw: dict) -> dict:
    zone_feature = next(feature for feature in result["features"]
                        if feature["properties"]["feature_kind"] == "inspection_zone")
    zone = shape(zone_feature["geometry"])
    counts = {"buildings": 0, "trees": 0}
    for feature in buildings_raw.get("features", []):
        if not shape(feature["geometry"]).intersects(zone):
            continue
        source = feature.get("properties", {})
        result["features"].append({
            "type": "Feature", "geometry": feature["geometry"],
            "properties": {
                "feature_kind": "building_check", "osm_id": source.get("osm_id"),
                "name": source.get("building_name") or source.get("name"),
                "height_m": source.get("height_m"),
                "height_method": source.get("height_method") or source.get("height_source"),
                "confidence": source.get("confidence"),
                "source_field_verified": source.get("field_verified"),
                "presence_verified": None, "dimensions_verified": None, "notes": None,
            },
        })
        counts["buildings"] += 1
    for feature in trees_raw.get("features", []):
        if not shape(feature["geometry"]).intersects(zone):
            continue
        source = feature.get("properties", {})
        result["features"].append({
            "type": "Feature", "geometry": feature["geometry"],
            "properties": {
                "feature_kind": "tree_check", "tree_id": source.get("tree_id"),
                "common": source.get("common"), "height_m": source.get("height_m"),
                "crown_radius_m": source.get("crown_radius_m"),
                "height_method": source.get("height_method"),
                "crown_method": source.get("crown_method"),
                "presence_verified": None, "dimensions_verified": None, "notes": None,
            },
        })
        counts["trees"] += 1
    result["metadata"]["obstruction_checks"] = counts
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin-place", required=True)
    parser.add_argument("--destination-place", required=True)
    parser.add_argument("--departure-time", type=datetime.fromisoformat, required=True)
    parser.add_argument("--temperature-c", type=float, required=True)
    parser.add_argument("--buildings", type=Path, required=True)
    parser.add_argument("--trees", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--confirm-unverified-preview", action="store_true")
    args = parser.parse_args()
    try:
        if not args.confirm_unverified_preview:
            raise ValueError("Pass --confirm-unverified-preview; this never verifies coverage")
        if args.departure_time.utcoffset() is None:
            raise ValueError("Departure time must include a timezone offset")
        if not -20 <= args.temperature_c <= 55:
            raise ValueError("Temperature must be between -20 and 55 Celsius")
        origin = find_place(args.origin_place)
        destination = find_place(args.destination_place)
        if origin is None or destination is None:
            raise ValueError("Unknown place ID")
        graph = load_graph()
        model = load_model()
        if graph is None or model is None:
            raise ValueError("Walking graph and shade inputs must be loaded")

        route_scope = route_candidate_envelopes(graph, origin.coordinate, destination.coordinate)
        corridor_bbox = tuple(route_scope["maximum_shade"]["bbox"])
        input_extent = shadow_input_extent(
            args.buildings, args.trees, corridor_bbox, args.departure_time)
        if input_extent["status"] != "checked" or not all(
            input_extent[source]["contains_buffered_candidates"] for source in ("buildings", "trees")
        ):
            raise ValueError("Source inputs do not cover the candidate routes plus shadow buffer")

        buildings_raw = json.loads(args.buildings.read_text(encoding="utf-8"))
        trees_raw = json.loads(args.trees.read_text(encoding="utf-8"))
        building_bbox = buildings_raw.get("metadata", {}).get("source_bbox")
        tree_bbox = trees_raw.get("metadata", {}).get("study_bbox")
        common = box(*building_bbox).intersection(box(*tree_bbox))
        assumed = ShadeModel(model.shapes, model.data_as_of, True,
                             _project_polygon(mapping(common)), model.source, model.trees)
        service.load_model = lambda: assumed
        response = service.build_routes(
            origin.coordinate, destination.coordinate, args.departure_time, args.temperature_c)
        if any(route.sun_seconds is None or route.unknown_seconds > .01 for route in response.routes):
            raise ValueError("Preview routes must be completely scored before field export")

        result = build_audit_geojson(
            response, origin_id=origin.id, destination_id=destination.id,
            when=args.departure_time, temperature_c=args.temperature_c,
            building_reach_m=input_extent["buildings"]["max_shadow_reach_m"],
            tree_reach_m=input_extent["trees"]["max_shadow_reach_m"],
            candidate_bbox=corridor_bbox,
        )
        add_obstruction_checks(result, buildings_raw, trees_raw)
        result["metadata"].update(
            route_scope=route_scope,
            input_extent=input_extent,
            inputs={
                "buildings": file_identity(args.buildings),
                "trees": file_identity(args.trees),
                "graph": file_identity(GRAPH_FILE),
            },
        )
        result["metadata"]["structure_sha256"] = structure_sha256(result)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        checks = sum(feature["properties"]["feature_kind"] == "field_check"
                     for feature in result["features"])
        print(json.dumps({"output": str(args.out), "routes": 3, "field_checks": checks,
                          "obstruction_checks": result["metadata"]["obstruction_checks"],
                          "coverage_complete_verified": False}, indent=2))
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, f"Cannot export field audit: {error}\n")


if __name__ == "__main__":
    main()
