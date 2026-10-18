"""The multi-step jobs behind each request, and how their results read in a chat."""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from visionlab.analyze import analyze_area, land_cover, train_from_examples
from visionlab.compare import meters
from visionlab.imagery import ImageryUnavailable
from visionlab.models import PixelModel
from visionlab.requests import DATASETS, HELP, Request

RESULTS = Path(__file__).resolve().parents[1] / "data" / "results"
# the shady business backend, if it's running, plans real walking routes;
# without it a walk is sampled along the straight line
ROUTING = "http://127.0.0.1:8000/api/routes"
STEP_M = 120


def _dataset(name: str | None) -> list[dict] | None:
    if not name:
        return None
    raw = json.loads(DATASETS[name].read_text(encoding="utf-8"))
    return [f for f in raw["features"] if (f.get("geometry") or {}).get("type") in ("Point", "Polygon", "MultiPolygon")]


def _walk_line(a: tuple[float, float], b: tuple[float, float]) -> tuple[list[tuple[float, float]], str]:
    body = json.dumps({"origin": {"coordinate": list(a)}, "destination": {"coordinate": list(b)},
                       "departure_time": datetime.now(timezone.utc).isoformat(), "temperature_c": 25}).encode()
    try:
        request = urllib.request.Request(ROUTING, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=40) as response:
            routes = json.load(response)["routes"]
        fastest = next(r for r in routes if r["mode"] == "fastest")
        return [tuple(c) for c in fastest["geometry"]["coordinates"]], "walking route from the Shady Business router"
    except Exception:
        return [a, b], "straight line (routing service not reachable)"


def _samples(line: list[tuple[float, float]], step_m: float) -> list[tuple[float, float]]:
    points, walked, next_at = [line[0]], 0.0, step_m
    for p, q in zip(line, line[1:]):
        length = meters(p, q)
        while length and next_at <= walked + length:
            t = (next_at - walked) / length
            points.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
            next_at += step_m
        walked += length
    if meters(points[-1], line[-1]) > step_m / 3:
        points.append(line[-1])
    return points


def _save(kind: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{kind}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def summary_json(result: dict) -> dict:
    """The part of a result that fits in a chat; the full GeoJSON is saved alongside."""
    keep = {k: result[k] for k in ("target", "model", "center", "size_m", "coverage_share", "area_m2", "imagery") if k in result}
    keep["polygons"] = len(result["polygons"]["features"])
    if "crowns" in result:
        keep["crowns"] = len(result["crowns"])
        keep["crown_examples"] = result["crowns"][:5]
        keep["ground"] = {k: v for k, v in result["ground"].items() if not k.endswith("_polygons")}
    if "comparison" in result:
        keep["comparison"] = {k: v for k, v in result["comparison"].items() if k != "new_indices"}
    return keep


def run(request: Request) -> str:
    """Do the job and write the reply. Tool failures come back as a clear message, never a crash."""
    try:
        if request.action == "help":
            return HELP
        if request.action == "models":
            trained = PixelModel.available()
            return ("**Built-in** (no training needed): vegetation, water, shadow.\n**Trained**: "
                    + (", ".join(trained) if trained else "none yet") + ".\nSend labeled GeoJSON to train a new one.")
        if request.action == "train":
            return _train(request)
        if not request.places:
            return ("I couldn't tell where to look. Name a place (e.g. *Olympic Hall*) or give coordinates "
                    "like *34.0724, -118.4536*.")
        if request.action == "path":
            return _path(request)
        return _area(request)
    except ImageryUnavailable as exc:
        return f"I couldn't get aerial imagery for that area ({exc}). It may be outside NAIP coverage (the US only), or the service is busy; try again in a minute."
    except Exception as exc:  # the agent must keep answering even when a step fails
        return f"Something went wrong while working on that: `{type(exc).__name__}: {exc}`. Try a smaller area or rephrase."


def _cover(request: Request) -> str:
    name, lon, lat = request.places[0]
    result = land_cover(lon, lat, request.size_m)
    path = _save("cover", result)
    labels = {"tree_canopy": "Tree canopy", "other_vegetation": "Lawn / low vegetation", "building": "Roofs",
              "water": "Water", "ground_shade": "Ground in shade", "ground_sun": "Ground in sun"}
    heights = [c["height_m"] for c in result["crowns"] if c.get("height_m")]
    lines = [f"**Land cover around {name}** ({result['size_m']:.0f} m square, imagery {result['imagery']['captured']})", "",
             "| class | share | polygons |", "|---|---|---|"]
    lines += [f"| {labels[k]} | {v:.0%} | {len(result['layers'][k]['features'])} |" for k, v in result["shares"].items()]
    lines += ["", f"- **{len(result['crowns'])} tree crowns**" + (f", estimated {min(heights):.0f}–{max(heights):.0f} m tall." if heights else "."),
              f"- Of the open ground, **{result['ground_shade_share']:.0%} is in shade** at photo time.",
              (f"- Wildfire defensible space: **{result['defensible_space']['vegetation_share_in_zone']:.0%}** of the ground within 30 m of the roofs "
               f"is vegetation ({result['defensible_space']['tree_canopy_share_in_zone']:.0%} tree canopy)."
               if result.get("defensible_space") else "- No roofs found, so no defensible-space zone."),
              "\n```json\n" + json.dumps({k: result[k] for k in ("center", "size_m", "shares", "ground_shade_share", "defensible_space", "models", "imagery")}, indent=1) + "\n```",
              f"Every class as GeoJSON polygons saved as `{path.name}`."]
    return "\n".join(lines)


def _area(request: Request) -> str:
    if request.target == "land_cover":
        return _cover(request)
    name, lon, lat = request.places[0]
    reference = _dataset(request.compare)
    result = analyze_area(lon, lat, request.size_m, request.target, reference=reference)
    path = _save("area", result)
    lines = [f"**{request.target.replace('_', ' ').title()} around {name}** ({result['size_m']:.0f} m square, "
             f"imagery {result['imagery']['captured']}, model `{result['model']}`)",
             f"- Covers **{result['coverage_share']:.0%}** of the area ({result['area_m2']:,.0f} m²) in "
             f"{len(result['polygons']['features'])} polygons."]
    if request.target == "building" and result.get("height_model"):
        hs = [f["properties"]["height_m"] for f in result["polygons"]["features"] if f["properties"].get("height_m")]
        if hs:
            lines.append(f"- Estimated heights {min(hs):.0f}–{max(hs):.0f} m from roof size (±{result['height_model']['mean_abs_error_m']:.1f} m).")
    if "crowns" in result:
        heights = [c["height_m"] for c in result["crowns"] if c.get("height_m")]
        lines.append(f"- **{len(result['crowns'])} tree crowns**" + (f", estimated {min(heights):.0f}–{max(heights):.0f} m tall "
                     f"(height from crown width, ±{result['height_model']['mean_abs_error_m']:.1f} m)" if heights else "") + ".")
        lines.append(f"- Open ground in shade at photo time: **{result['ground']['shade_share_of_open_ground']:.0%}**.")
    if "comparison" in result:
        c = result["comparison"]
        if c["reference_covers_area"]:
            lines.append(f"- Against **{request.compare}**: {c['reference_objects_in_area']} known here, "
                         f"{c['matched']} matched, {c['reference_under_detected_area']} under what I detected, "
                         f"**{c['new_not_in_reference']} detections not in the dataset**.")
        else:
            lines.append(f"- **{request.compare}** has nothing recorded here, so all {c['new_not_in_reference']} detections are new to it: "
                         "this is a gap in the dataset.")
    lines.append(f"\n```json\n{json.dumps(summary_json(result), indent=1)[:2500]}\n```\nFull GeoJSON saved as `{path.name}`.")
    return "\n".join(lines)


def _path(request: Request) -> str:
    (a_name, *a), (b_name, *b) = request.places[:2]
    line, how = _walk_line(tuple(a), tuple(b))
    points = _samples(line, STEP_M)[:12]  # a cap so one request stays under a minute
    reference = _dataset(request.compare or "ucla trees")
    stretches, crowns_total, new_total, gaps = [], 0, 0, 0
    for i, (lon, lat) in enumerate(points):
        result = analyze_area(lon, lat, STEP_M, "tree_canopy", reference=reference)
        comp = result["comparison"]
        crowns_total += len(result["crowns"])
        new_total += comp["new_not_in_reference"]
        gaps += not comp["reference_covers_area"]
        stretches.append({"at_m": i * STEP_M, "center": [round(lon, 6), round(lat, 6)], "canopy_share": result["coverage_share"],
                          "crowns": len(result["crowns"]), "shade_share_of_open_ground": result["ground"]["shade_share_of_open_ground"],
                          "dataset_covers": comp["reference_covers_area"], "new_trees": comp["new_not_in_reference"]})
    path = _save("path", {"from": a_name, "to": b_name, "line": line, "how": how, "stretches": stretches})
    canopy = sum(s["canopy_share"] for s in stretches) / len(stretches)
    lines = [f"**Trees and shade from {a_name} to {b_name}** ({len(stretches)} stretches of {STEP_M} m along a {how})",
             f"- Average canopy over the path: **{canopy:.0%}**; **{crowns_total} crowns** found.",
             f"- **{gaps} of {len(stretches)} stretches** aren't covered by the UCLA trees inventory at all; "
             f"**{new_total} detected trees** are missing from it." if gaps else
             f"- The inventory covers every stretch; {new_total} detected crowns aren't in it.",
             "", "| m | canopy | crowns | shade on open ground | in inventory? | new trees |", "|---|---|---|---|---|---|"]
    lines += [f"| {s['at_m']} | {s['canopy_share']:.0%} | {s['crowns']} | {s['shade_share_of_open_ground']:.0%} | "
              f"{'yes' if s['dataset_covers'] else '**no**'} | {s['new_trees']} |" for s in stretches]
    lines.append(f"\nShade is as seen in the aerial photo; it moves through the day. Full results saved as `{path.name}`.")
    return "\n".join(lines)


def _train(request: Request) -> str:
    if not request.url or not request.name:
        return "To train, say: *train <name> from <URL of a GeoJSON with example polygons>*."
    with urllib.request.urlopen(urllib.request.Request(request.url, headers={"User-Agent": "visionlab/0.1"}), timeout=30) as r:
        examples = json.load(r)["features"]
    report = train_from_examples(request.name, examples)
    return (f"Trained **{request.name}** on {report['examples']} examples across {report['tiles']} tiles "
            f"({report['pixels']:,} pixels). Ask me to find {request.name.replace('_', ' ')} anywhere with NAIP imagery.")
