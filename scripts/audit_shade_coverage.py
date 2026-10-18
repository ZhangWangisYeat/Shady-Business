#!/usr/bin/env python3
"""Read-only gate for promoting a local demo corridor from unknown to sun/shade."""
import argparse
from datetime import datetime
import json
from math import isfinite, radians, sqrt, tan
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from shapely.geometry import box, mapping, shape

from app.routing.candidates import bounded_edge_refs, fastest_edge_path
from app.routing.graph import coords_for_edge, load_graph, snap_node
from app.routing.policy import recommended_detour_fraction
from app.shade.model import MIN_SOLAR_ELEVATION, _project_polygon, read_model, solar_angles
from app.shade.trees import read_tree_model


def _known_height(feature: dict) -> bool:
    value = feature.get("properties", {}).get("height_m")
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and isfinite(value) and 1 <= value <= 250)


def route_candidate_envelopes(graph, origin: tuple[float, float],
                              destination: tuple[float, float]) -> dict:
    """Bounds every graph edge eligible for any of the three route modes."""
    source = snap_node(graph, origin)
    target = snap_node(graph, destination)
    _, fastest_duration = fastest_edge_path(graph, source, target, 1.3)
    caps = {
        "recommended": fastest_duration * (1 + recommended_detour_fraction(55)),
        "maximum_shade": min(fastest_duration * 1.6, fastest_duration + 720),
    }
    report = {"fastest_duration_s": fastest_duration}
    for mode, cap in caps.items():
        edges = bounded_edge_refs(graph, source, target, cap, 1.3)
        coordinates = [point for edge in edges for point in coords_for_edge(graph, *edge)]
        if not coordinates:
            raise ValueError(f"No eligible {mode} edges")
        report[mode] = {
            "max_duration_s": cap,
            "eligible_edges": len(edges),
            "bbox": [
                min(point[0] for point in coordinates),
                min(point[1] for point in coordinates),
                max(point[0] for point in coordinates),
                max(point[1] for point in coordinates),
            ],
        }
    return report


def shadow_input_extent(buildings_path: Path, trees_path: Path,
                        corridor_bbox: tuple[float, float, float, float],
                        when: datetime) -> dict:
    """Check that source extracts extend beyond routes by the modeled shadow reach.

    Passing this only proves spatial input extent, never real-world completeness.
    """
    if when.utcoffset() is None:
        raise ValueError("Departure time must include a timezone offset")
    buildings_raw = json.loads(buildings_path.read_text(encoding="utf-8"))
    trees_raw = json.loads(trees_path.read_text(encoding="utf-8"))
    building_model = read_model(buildings_path)
    tree_model = read_tree_model(trees_path)
    elevation, azimuth = solar_angles(when)
    result = {"departure_time": when.isoformat(), "solar_elevation_deg": elevation,
              "solar_azimuth_deg": azimuth, "status": "checked"}
    if elevation <= MIN_SOLAR_ELEVATION:
        result.update(status="not_modeled", reason="Sun is below the reliable shadow threshold")
        return result

    cotangent = 1 / tan(radians(elevation))
    building_reach = max((height * cotangent for _, height in building_model.shapes), default=0.0)
    tree_reach = 0.0
    for tree in tree_model.trees:
        radius = tree.crown_radius_m
        vertical_radius = (min(radius, tree.height_m / 2) if tree.crown_base_m is None
                           else (tree.height_m - tree.crown_base_m) / 2)
        center_height = tree.height_m - vertical_radius
        major = sqrt(radius * radius + (vertical_radius * cotangent) ** 2)
        tree_reach = max(tree_reach, center_height * cotangent + major)

    corridor = _project_polygon(mapping(box(*corridor_bbox)))

    def extent(metadata: dict, key: str, reach_m: float) -> dict:
        bounds = metadata.get(key)
        if not isinstance(bounds, list) or len(bounds) != 4:
            return {"source_bbox": bounds, "max_shadow_reach_m": reach_m,
                    "contains_buffered_candidates": False}
        source = _project_polygon(mapping(box(*bounds)))
        return {"source_bbox": bounds, "max_shadow_reach_m": reach_m,
                "contains_buffered_candidates": source.covers(corridor.buffer(reach_m))}

    result["buildings"] = extent(buildings_raw.get("metadata", {}), "source_bbox", building_reach)
    result["trees"] = extent(trees_raw.get("metadata", {}), "study_bbox", tree_reach)
    return result


def audit(buildings_path: Path, trees_path: Path,
          corridor_bbox: tuple[float, float, float, float]) -> dict:
    buildings_raw = json.loads(buildings_path.read_text(encoding="utf-8"))
    trees_raw = json.loads(trees_path.read_text(encoding="utf-8"))
    building_model = read_model(buildings_path)
    tree_model = read_tree_model(trees_path)
    corridor_wgs84 = box(*corridor_bbox)
    corridor = _project_polygon(mapping(corridor_wgs84))
    building_meta = buildings_raw.get("metadata", {})
    tree_meta = trees_raw.get("metadata", {})
    blockers = []

    building_report = building_meta.get("import_report", {})
    building_consistent = building_report.get("buildings") == len(buildings_raw.get("features", []))
    if not building_consistent:
        blockers.append({"code": "building_import_accounting_inconsistent"})
    tree_report = tree_meta.get("import_report", {})
    tree_accounted = sum(tree_report.get(key, 0) for key in (
        "outside_study_rectangle", "invalid_coordinates", "non_tree_records",
        "standing_tree_records"))
    tree_consistent = (tree_report.get("source_rows") == tree_accounted
                       and tree_report.get("standing_tree_records") == len(trees_raw.get("features", [])))
    if not tree_consistent:
        blockers.append({"code": "tree_import_accounting_inconsistent"})

    unknown_features = [feature for feature in buildings_raw.get("features", [])
                        if not _known_height(feature)]
    unknown_buildings = len(unknown_features)
    unknown_manifest = []
    for feature in unknown_features:
        props = feature.get("properties", {})
        geometry = shape(feature["geometry"])
        unknown_manifest.append({
            "osm_id": props.get("osm_id"),
            "name": props.get("name"),
            "height_source": props.get("height_source"),
            "intersects_corridor": geometry.intersects(corridor_wgs84),
        })
    if unknown_buildings:
        blockers.append({"code": "building_unknown_heights", "count": unknown_buildings})
    if building_meta.get("coverage_complete_verified") is not True:
        blockers.append({"code": "building_coverage_unverified"})
    if building_meta.get("coverage_geometry") is None:
        blockers.append({"code": "building_coverage_geometry_missing"})
    if tree_model.unmodeled_records:
        blockers.append({"code": "tree_unmodeled_records", "count": tree_model.unmodeled_records})
    if tree_meta.get("coverage_complete_verified") is not True:
        blockers.append({"code": "tree_coverage_unverified"})
    if tree_meta.get("coverage_geometry") is None:
        blockers.append({"code": "tree_coverage_geometry_missing"})

    building_coverage = (_project_polygon(building_meta["coverage_geometry"])
                         if building_meta.get("coverage_geometry") is not None else None)
    tree_coverage = tree_model.coverage_geometry
    if building_coverage is not None and not building_coverage.covers(corridor):
        blockers.append({"code": "corridor_outside_building_coverage"})
    if tree_coverage is not None and not tree_coverage.covers(corridor):
        blockers.append({"code": "corridor_outside_tree_coverage"})

    return {
        "ready": not blockers,
        "corridor_bbox": list(corridor_bbox),
        "buildings": {"features": len(buildings_raw.get("features", [])),
                      "modeled": len(building_model.shapes) if building_model else 0,
                      "unknown_heights": unknown_buildings,
                      "unknown_height_manifest": unknown_manifest},
        "trees": {"features": len(trees_raw.get("features", [])),
                  "modeled": len(tree_model.trees),
                  "unmodeled": tree_model.unmodeled_records},
        "source_accounting": {
            "buildings": {
                "retained": len(buildings_raw.get("features", [])),
                "explicitly_excluded": building_report.get("excluded_unnamed_features", 0),
                "consistent": building_consistent,
            },
            "trees": {
                "source_rows": tree_report.get("source_rows"),
                "accounted_rows": tree_accounted,
                "retained": len(trees_raw.get("features", [])),
                "consistent": tree_consistent,
            },
        },
        "blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buildings", type=Path, required=True)
    parser.add_argument("--trees", type=Path, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--corridor-bbox", type=float, nargs=4,
                       metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    scope.add_argument("--route", type=float, nargs=4,
                       metavar=("ORIGIN_LON", "ORIGIN_LAT", "DEST_LON", "DEST_LAT"),
                       help="derive coverage from every edge eligible for all three modes")
    parser.add_argument("--departure-time", type=datetime.fromisoformat,
                        help="offset-aware time used to verify the external shadow-caster buffer")
    args = parser.parse_args()
    try:
        route_candidates = None
        corridor_bbox = tuple(args.corridor_bbox) if args.corridor_bbox else None
        if args.route:
            if args.departure_time is None:
                raise ValueError("--route requires --departure-time")
            graph = load_graph()
            if graph is None:
                raise ValueError("OSM walking graph is not loaded")
            route_candidates = route_candidate_envelopes(
                graph, tuple(args.route[:2]), tuple(args.route[2:]))
            corridor_bbox = tuple(route_candidates["maximum_shade"]["bbox"])
        report = audit(args.buildings, args.trees, corridor_bbox)
        if route_candidates is not None:
            report["route_candidates"] = route_candidates
            report["input_extent"] = shadow_input_extent(
                args.buildings, args.trees, corridor_bbox, args.departure_time)
            if report["input_extent"]["status"] == "checked":
                for source in ("buildings", "trees"):
                    if not report["input_extent"][source]["contains_buffered_candidates"]:
                        report["blockers"].append({"code": f"{source}_source_extent_too_small"})
            report["ready"] = not report["blockers"]
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, f"Invalid shade coverage input: {error}\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
