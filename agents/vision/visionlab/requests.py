"""Understanding a chat request: what to look for, where, how big an area, and against which dataset."""
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from visionlab.analyze import ALIASES, resolve_target
from visionlab.models import PixelModel

REPO = Path(__file__).resolve().parents[3]
PLACES = REPO / "backend" / "app" / "places" / "ucla_places.json"
# datasets the agent can compare against by name; the arborpro csv joins this
# list once it's imported
DATASETS = {"ucla trees": REPO / "backend" / "data" / "ucla_trees.geojson",
            "ucla buildings": REPO / "backend" / "data" / "ucla_buildings.geojson"}
COORD = re.compile(r"(-?\d{1,3}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})")
SIZE = re.compile(r"(\d{2,4})\s*(?:m\b|meters?|metres?)", re.I)
URL = re.compile(r"https?://\S+\.geojson\S*", re.I)


@dataclass
class Request:
    action: str  # analyze, path, train, models, help
    target: str | None = None
    places: list[tuple[str, float, float]] = field(default_factory=list)
    size_m: float = 160
    compare: str | None = None
    url: str | None = None
    name: str | None = None


def _places() -> list[dict]:
    if not PLACES.exists():
        return []
    raw = json.loads(PLACES.read_text(encoding="utf-8"))
    return raw["places"] if isinstance(raw, dict) else raw


def find_places(text: str) -> list[tuple[str, float, float]]:
    """Place names in the text, in the order they appear: campus catalog first, then coordinates."""
    found = []
    lowered = text.lower()
    # longest names first, so "Royce Hall" wins over "Royce"
    for place in sorted(_places(), key=lambda p: -len(p["name"])):
        name = place["name"].lower()
        at = lowered.find(name)
        if len(name) >= 5 and at >= 0 and not any(at < end and at + len(name) > start for _, _, _, start, end in found):
            found.append((place["name"], *place["coordinate"], at, at + len(name)))
    for match in COORD.finditer(text):
        lat, lon = float(match.group(1)), float(match.group(2))
        if abs(lat) > 90:  # written lon, lat
            lat, lon = lon, lat
        found.append((f"{lat:.5f}, {lon:.5f}", lon, lat, match.start(), match.end()))
    return [(n, lon, lat) for n, lon, lat, _, _ in sorted(found, key=lambda f: f[3])]


def geocode(query: str) -> tuple[str, float, float] | None:
    """Anywhere else in the world, through OpenStreetMap's free geocoder (one request, as its policy asks)."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "visionlab/0.1 (LA Hacks 2026)"}), timeout=15) as r:
            hits = json.load(r)
        time.sleep(1)
    except Exception:
        return None
    return (hits[0]["display_name"].split(",")[0], float(hits[0]["lon"]), float(hits[0]["lat"])) if hits else None


def parse(text: str) -> Request:
    lowered = text.lower()
    if re.search(r"\b(models?|what can you (detect|find)|targets)\b", lowered) and "train" not in lowered:
        return Request("models")
    if re.search(r"\b(help|how do i|what (?:do|can) you do|who are you|hi|hello)\b", lowered) and not find_places(text):
        return Request("help")
    size = SIZE.search(text)
    compare = next((name for name in DATASETS if name in lowered), None)
    if compare is None and re.search(r"\b(inventory|dataset|compare)\b", lowered):
        # "compare with the dataset" picks the one that fits what's being looked for
        compare = "ucla buildings" if re.search(r"\b(buildings?|roofs?)\b", lowered) else "ucla trees"
    if "train" in lowered or "teach" in lowered:
        url = URL.search(text)
        name = re.search(r"(?:train|teach)\s+(?:a\s+|an\s+|me\s+)?(?:model\s+(?:for|called)\s+)?([a-z][a-z _-]{2,30}?)\s+(?:from|using|with)\b", lowered)
        return Request("train", url=url.group(0) if url else None,
                       name=name.group(1).strip().replace(" ", "_") if name else None)
    places = find_places(text)
    target = resolve_target(text) or "tree_canopy"
    path = re.search(r"\bfrom\b.+\bto\b", lowered) or re.search(r"\b(walk|path|route|along)\b", lowered)
    if not places:
        # "the area around X": hand the bit after "at/near/around" to the geocoder
        where = re.search(r"\b(?:at|near|around|in|of)\s+(.+?)(?:\s+(?:within|radius|and|compare|with)\b|[?.!]|$)", text, re.I)
        hit = geocode(where.group(1)) if where else None
        places = [hit] if hit else []
    return Request("path" if path and len(places) >= 2 else "analyze", target, places,
                   float(size.group(1)) if size else 160, compare)


HELP = f"""I'm **VisionLab**, a vision agent that turns images into data. Tell me what to look for and where. I'll get the aerial imagery (USDA NAIP, 0.6 m, with near infrared), detect and outline it, and return polygons and measurements as JSON. I also compare what I see with real datasets to find what's missing, and predict values nobody measured (like tree or building heights).

Things to try:
- "Classify the land cover around Royce Hall": trees, lawn, roofs, water, shaded and sunny ground, plus vegetation near buildings (wildfire defensible space)
- "Find tree canopy at Olympic Hall and compare with the UCLA trees inventory"
- "Find the buildings near Pauley Pavilion and compare with the dataset"
- "Map the trees and shade along the walk from Olympic Hall to Royce Hall"
- "Where is the water near 34.0689, -118.4452 within 300 m?"
- "Train solar panels from https://example.com/panels.geojson"

Targets I know: {", ".join(sorted(set(ALIASES) | set(PixelModel.available())))}."""
