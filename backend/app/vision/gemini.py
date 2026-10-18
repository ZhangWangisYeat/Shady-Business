"""Asking Gemini to map trees, ground shade and buildings in one photo, as strict JSON."""
import base64
import json
import time
import urllib.error
import urllib.request
from typing import Callable

# flash is on the free tier and good at boxes and outlines. the free tier is
# limited per minute and per day (about 10 a minute and 250 a day for flash
# when this was written; check aistudio.google.com/rate-limit for yours), so
# every run has a hard call cap and a gap between calls.
DEFAULT_MODEL = "gemini-2.5-flash"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_S = 90

GRID = ("Positions use a 0-1000 grid over the image: x from 0 at the left edge to 1000 at the right, "
        "y from 0 at the top to 1000 at the bottom.")

AERIAL_PROMPT = """You are mapping shade for a campus walking app. This is a north-up aerial orthophoto
about {size_m:.0f} m across, centered on {name} ({lat:.5f}, {lon:.5f}), captured {captured}.
{grid}

Return JSON for:
1. trees: every tree crown you can see. Trace each crown's edge with 6 to 16 points. If crowns touch,
   split them where you can see separate trees; if a canopy is one continuous mass, return it once with
   kind "canopy_cluster". Use kind "shrub" for woody plants you judge under 2.5 m. Estimate height_m from
   crown size and the length of the shadow the tree casts (null if you really can't tell). confidence is
   how sure you are that it is a tree or shrub and not grass, a dark roof or a shadow.
2. ground: patches of open ground, paths and plazas, each labeled "shade" or "sun" as they are in this
   photo. Skip roofs. Trace with 4 to 16 points.
3. buildings: roof outlines with height_m estimated from their shadows (null if no shadow is visible).

Be conservative: fewer, accurate outlines beat many rough ones. Don't invent anything outside the image.
At most 60 trees, 20 ground patches and 15 buildings."""

STREET_PROMPT = """You are mapping shade for a campus walking app. This is a street-level photo taken near
{name} at ({lat:.5f}, {lon:.5f}), with the camera facing {heading:.0f} degrees from north{pano}, captured
{captured}. {grid}

Return JSON for:
1. trees: each tree (or shrub) you can see. box is [x_min, y_min, x_max, y_max]. trunk_x is the column
   where the trunk meets the ground (null if hidden). distance_m is how far the trunk is from the
   camera. Estimate height_m and crown_width_m in meters. kind and confidence as for an aerial map:
   "tree", "canopy_cluster" or "shrub", and how sure you are it is vegetation.
2. ground: the share of the visible ground (0 to 1) in shade and in sun, and whether the spot where the
   camera stands is in shade.
3. buildings: box, distance_m and height_m for buildings that would throw shade on the path.

Be conservative and skip anything further than 60 m. At most 25 trees and 8 buildings."""

_POINT = {"type": "OBJECT", "properties": {"x": {"type": "NUMBER"}, "y": {"type": "NUMBER"}}, "required": ["x", "y"]}
_OUTLINE = {"type": "ARRAY", "items": _POINT}
_KIND = {"type": "STRING", "enum": ["tree", "canopy_cluster", "shrub"]}
_HEIGHT = {"type": "NUMBER", "nullable": True}

AERIAL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "trees": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "kind": _KIND, "outline": _OUTLINE, "height_m": _HEIGHT, "confidence": {"type": "NUMBER"},
            "species_guess": {"type": "STRING", "nullable": True}},
            "required": ["kind", "outline", "height_m", "confidence"]}},
        "ground": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "state": {"type": "STRING", "enum": ["shade", "sun"]}, "outline": _OUTLINE},
            "required": ["state", "outline"]}},
        "buildings": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "outline": _OUTLINE, "height_m": _HEIGHT}, "required": ["outline", "height_m"]}},
        "notes": {"type": "STRING", "nullable": True},
    },
    "required": ["trees", "ground", "buildings"],
}

_BOX = {"type": "ARRAY", "items": {"type": "NUMBER"}}
STREET_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "trees": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "kind": _KIND, "box": _BOX, "trunk_x": {"type": "NUMBER", "nullable": True},
            "distance_m": {"type": "NUMBER"}, "height_m": _HEIGHT, "crown_width_m": _HEIGHT,
            "confidence": {"type": "NUMBER"}},
            "required": ["kind", "box", "distance_m", "height_m", "crown_width_m", "confidence"]}},
        "ground": {"type": "OBJECT", "properties": {
            "shade_share": {"type": "NUMBER"}, "sun_share": {"type": "NUMBER"},
            "camera_in_shade": {"type": "BOOLEAN", "nullable": True}},
            "required": ["shade_share", "sun_share"]},
        "buildings": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "box": _BOX, "distance_m": {"type": "NUMBER"}, "height_m": _HEIGHT},
            "required": ["box", "distance_m", "height_m"]}},
        "notes": {"type": "STRING", "nullable": True},
    },
    "required": ["trees", "ground", "buildings"],
}


class QuotaReached(Exception):
    """Gemini said slow down (429) or the run's own call cap is used up."""


def build_request(image: bytes, mime: str, photo: dict, thinking_budget: int = 512) -> dict:
    aerial = photo["kind"] == "aerial"
    prompt = (AERIAL_PROMPT if aerial else STREET_PROMPT).format(
        grid=GRID, name=photo["site_name"], lat=photo["coordinate"][1], lon=photo["coordinate"][0],
        size_m=photo.get("size_m", 0), captured=photo.get("captured_at") or "at an unknown time",
        heading=photo.get("heading") or 0, pano=" (a 360 panorama, camera heading in the middle)" if photo.get("panorama") else "")
    return {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}}]}],
        "generationConfig": {
            # the same photo should give the same map every run
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": AERIAL_SCHEMA if aerial else STREET_SCHEMA,
            # a little thinking helps with splitting touching crowns, and the
            # cap keeps each call's token use (and the per-minute limit) small
            "thinkingConfig": {"thinkingBudget": thinking_budget},
        },
    }


def _clamp(value, low=0.0, high=1000.0):
    return max(low, min(high, float(value)))


def _outline(points) -> list[tuple[float, float]]:
    return [(_clamp(p["x"]), _clamp(p["y"])) for p in points or [] if "x" in p and "y" in p]


def _height(value, high=80.0):
    return float(value) if isinstance(value, (int, float)) and 0 < value <= high else None


def parse_response(response: dict, kind: str) -> dict:
    """The detections, cleaned up: out-of-range numbers clamped, broken shapes dropped."""
    try:
        text = response["candidates"][0]["content"]["parts"][0]["text"]
        raw = json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Gemini didn't return the expected JSON: {exc}") from exc
    trees, buildings = [], []
    if kind == "aerial":
        for t in raw.get("trees", []):
            outline = _outline(t.get("outline"))
            if len(outline) >= 3:
                trees.append({"kind": t.get("kind", "tree"), "outline": outline, "height_m": _height(t.get("height_m")),
                              "confidence": _clamp(t.get("confidence", 0), 0, 1), "species_guess": t.get("species_guess")})
        ground = [{"state": g["state"], "outline": _outline(g.get("outline"))} for g in raw.get("ground", [])
                  if g.get("state") in ("shade", "sun") and len(_outline(g.get("outline"))) >= 3]
        for b in raw.get("buildings", []):
            outline = _outline(b.get("outline"))
            if len(outline) >= 3:
                buildings.append({"outline": outline, "height_m": _height(b.get("height_m"), 150)})
    else:
        for t in raw.get("trees", []):
            box = t.get("box") or []
            distance = t.get("distance_m")
            if len(box) == 4 and isinstance(distance, (int, float)) and 0 < distance <= 60:
                trees.append({"kind": t.get("kind", "tree"), "box": [_clamp(v) for v in box],
                              "trunk_x": _clamp(t["trunk_x"]) if isinstance(t.get("trunk_x"), (int, float)) else None,
                              "distance_m": float(distance), "height_m": _height(t.get("height_m")),
                              "crown_width_m": _height(t.get("crown_width_m"), 40),
                              "confidence": _clamp(t.get("confidence", 0), 0, 1)})
        g = raw.get("ground") or {}
        ground = {"shade_share": _clamp(g.get("shade_share", 0), 0, 1), "sun_share": _clamp(g.get("sun_share", 0), 0, 1),
                  "camera_in_shade": g.get("camera_in_shade")}
        for b in raw.get("buildings", []):
            box = b.get("box") or []
            if len(box) == 4 and isinstance(b.get("distance_m"), (int, float)):
                buildings.append({"box": [_clamp(v) for v in box], "distance_m": float(b["distance_m"]),
                                  "height_m": _height(b.get("height_m"), 150)})
    usage = response.get("usageMetadata", {})
    return {"trees": trees, "ground": ground, "buildings": buildings, "notes": raw.get("notes"),
            "tokens": {"prompt": usage.get("promptTokenCount"), "output": usage.get("candidatesTokenCount"),
                       "thinking": usage.get("thoughtsTokenCount")}}


Post = Callable[[str, dict, dict], dict]


def _post(url: str, body: dict, headers: dict) -> dict:
    request = urllib.request.Request(url, json.dumps(body).encode(), {**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise QuotaReached("Gemini rate limit or daily quota reached (429)") from exc
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Gemini returned {exc.code}: {detail}") from exc


class Budget:
    """At most max_calls per run, at least min_interval_s apart.

    on a 429 it stops instead of retrying: on the free tier that means the
    minute or the day is used up, and retrying would only burn more of it.
    """

    def __init__(self, max_calls: int, min_interval_s: float, sleep=time.sleep, clock=time.monotonic):
        self.max_calls, self.min_interval_s, self.used = max_calls, min_interval_s, 0
        self._sleep, self._clock, self._last = sleep, clock, None

    def call(self, api_key: str, model: str, body: dict, post: Post = _post) -> dict:
        if self.used >= self.max_calls:
            raise QuotaReached(f"Stopped at this run's cap of {self.max_calls} Gemini calls")
        if self._last is not None:
            wait = self.min_interval_s - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self.used += 1
        self._last = self._clock()
        # the key goes in a header, not the url, so it never ends up in logs
        return post(API.format(model=model), body, {"x-goog-api-key": api_key})
