#!/usr/bin/env python3
"""Score a local route without running the API or contacting any provider.

Input: GeoJSON Feature/FeatureCollection of ordered, connected LineString edges;
each feature needs properties.duration_s. Output: internal scoring JSON.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.shade.model import build_shadow_field, read_model, with_tree_file
from app.shade.scoring import RouteEdge, score_route


def read_edges(path: Path) -> list[RouteEdge]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("type") == "Feature":
        features = [raw]
    elif raw.get("type") == "FeatureCollection":
        features = raw["features"]
    else:
        raise ValueError("Route must be a GeoJSON Feature or FeatureCollection")
    edges = []
    for feature in features:
        if feature.get("type") != "Feature" or feature["geometry"]["type"] != "LineString":
            raise ValueError("Each route feature must have LineString geometry")
        edges.append(RouteEdge(tuple(tuple(c) for c in feature["geometry"]["coordinates"]),
                               feature["properties"]["duration_s"]))
    return edges


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--buildings", type=Path, help="Optional license-cleared building GeoJSON")
    parser.add_argument("--trees", type=Path, help="Optional normalized local tree inventory GeoJSON")
    parser.add_argument("--departure", required=True, help="Offset-aware ISO 8601 time")
    parser.add_argument("--out", type=Path, help="Write output only when explicitly requested")
    args = parser.parse_args()
    try:
        edges = read_edges(args.route)
        model = read_model(args.buildings) if args.buildings else None
        if args.trees:
            model = with_tree_file(model, args.trees)
        field = build_shadow_field(model, datetime.fromisoformat(args.departure))
        result = score_route(edges, field)
        payload = json.dumps(result.to_dict(), indent=2, allow_nan=False)
        if args.out:
            args.out.write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, f"Invalid scoring input: {error}\n")


if __name__ == "__main__":
    main()
