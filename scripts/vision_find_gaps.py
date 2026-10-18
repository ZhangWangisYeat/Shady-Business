#!/usr/bin/env python3
"""Step 1 (offline): list route places and walkway stretches the tree inventory doesn't cover."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.vision.gaps import coverage_of, find_gap_sites, sample_route  # noqa: E402
from app.vision.geo import meters_between  # noqa: E402

VISION = ROOT / "backend/data/vision"
PLACES = ROOT / "backend/app/places/ucla_places.json"
TREES = ROOT / "backend/data/ucla_trees.geojson"


def route_line(origin: str, destination: str) -> list[tuple[float, float]]:
    from app.places.catalog import find_place
    from app.routing.service import build_routes
    a, b = find_place(origin), find_place(destination)
    if a is None or b is None:
        raise SystemExit(f"Unknown place id: {origin if a is None else destination}")
    result = build_routes(a.coordinate, b.coordinate, datetime.now(timezone.utc), 25)
    fastest = next(r for r in result.routes if r.mode == "fastest")
    return [tuple(c) for c in fastest.geometry.coordinates]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8, help="how many sites to keep (each costs photos and Gemini calls)")
    parser.add_argument("--focus", action="append", default=[], help="put sites whose name contains this first, e.g. --focus 'Olympic Hall'")
    parser.add_argument("--route", nargs=2, metavar=("ORIGIN_ID", "DESTINATION_ID"),
                        help="also sample the walk between two place ids every --every meters")
    parser.add_argument("--every", type=float, default=90, help="meters between route samples")
    parser.add_argument("--trees", type=Path, default=TREES)
    args = parser.parse_args()

    places = json.loads(PLACES.read_text(encoding="utf-8"))
    places = places["places"] if isinstance(places, dict) else places
    tree_file = json.loads(args.trees.read_text(encoding="utf-8"))
    coverage = coverage_of(tree_file)
    points = [tuple(f["geometry"]["coordinates"]) for f in tree_file["features"]]
    sites = find_gap_sites(places, points, coverage, focus=args.focus)
    outside = sum(s.reason == "outside_inventory" for s in sites)
    route_sites = sample_route(route_line(*args.route), coverage, args.every, f"{args.route[0]} to {args.route[1]}") if args.route else []
    # a route sample sitting on a gap place (the walk starts at Olympic Hall,
    # say) would photograph the same spot twice, so near-duplicates drop out
    chosen = []
    for site in route_sites + sites:
        if all(meters_between(site.coordinate, kept.coordinate) > 60 for kept in chosen):
            chosen.append(site)
    chosen = chosen[:args.limit]

    VISION.mkdir(parents=True, exist_ok=True)
    out = VISION / "gaps.json"
    out.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                               "tree_file": str(args.trees.name), "sites": [s.to_json() for s in chosen],
                               "all_gap_sites": len(sites), "outside_inventory_sites": outside}, indent=2), encoding="utf-8")
    print(f"{len(sites)} gap sites among {len(places)} places ({outside} outside the inventory's coverage).")
    for s in chosen:
        print(f"  {s.id:40s} {s.reason:18s} places={len(s.place_ids):2d} trees nearby={s.trees_nearby}")
    print(f"Wrote {len(chosen)} sites to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
