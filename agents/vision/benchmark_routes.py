#!/usr/bin/env python3
"""Same routes, same time and temperature, on the original data and on the VisionLab-filled data.

Run two backends, one on each dataset, and point this at their ports:

    agents\\.venv\\Scripts\\python agents/vision/benchmark_routes.py --before-port 8001 --after-port 8000
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROUTES = [("olympic-hall", "royce-hall"), ("bruin-plate", "royce-hall"), ("hedrick-hall", "powell-library")]
WHEN, TEMP_C = "2026-10-18T13:00:00-07:00", 32
OUT = Path(__file__).resolve().parent / "data" / "reports" / "route_benchmark.json"


def plan(port: int, origin: str, destination: str) -> list[dict]:
    body = json.dumps({"origin": {"place_id": origin}, "destination": {"place_id": destination},
                       "departure_time": WHEN, "temperature_c": TEMP_C}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/routes", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["routes"]


def summary(routes: list[dict]) -> dict:
    out = {}
    for r in routes:
        t = r["duration_s"]
        known_sun = sum(s["sun_seconds"] or 0 for s in r["segments"])
        out[r["mode"]] = {"minutes": round(t / 60, 1), "unknown_pct": round(100 * r["unknown_seconds"] / t, 1),
                          "sun_pct": round(100 * known_sun / t, 1), "shade_pct": round(100 * (t - r["unknown_seconds"] - known_sun) / t, 1),
                          "same_as": r["same_as"], "distinct_paths": None}
    out["distinct_paths"] = len({r["same_as"] or r["id"] for r in routes})
    return out


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--before-port", type=int, default=8000)
parser.add_argument("--after-port", type=int, default=8001)
parser.add_argument("--route", nargs=2, action="append", metavar=("ORIGIN_ID", "DESTINATION_ID"))
args = parser.parse_args()
results = []
for origin, destination in args.route or ROUTES:
    before, after = summary(plan(args.before_port, origin, destination)), summary(plan(args.after_port, origin, destination))
    results.append({"route": f"{origin} -> {destination}", "before": before, "after": after})
    print(f"\n{origin} -> {destination}   (distinct paths offered: {before['distinct_paths']} -> {after['distinct_paths']})")
    for mode in ("fastest", "recommended", "maximum_shade"):
        b, a = before[mode], after[mode]
        print(f"  {mode:14s} before {b['minutes']:4.1f} min unknown {b['unknown_pct']:5.1f}% shade {b['shade_pct']:5.1f}% sun {b['sun_pct']:5.1f}%"
              f"   after {a['minutes']:4.1f} min unknown {a['unknown_pct']:5.1f}% shade {a['shade_pct']:5.1f}% sun {a['sun_pct']:5.1f}%")
OUT.parent.mkdir(parents=True, exist_ok=True)
totals = {k: round(sum(r[k]["fastest"]["unknown_pct"] for r in results) / len(results), 1) for k in ("before", "after")}
print(f"\nAverage unknown on the fastest path: {totals['before']}% before, {totals['after']}% after.")
OUT.write_text(json.dumps({"when": WHEN, "temperature_c": TEMP_C, "average_fastest_unknown_pct": totals, "results": results}, indent=2), encoding="utf-8")
print(f"\nSaved {OUT}")
