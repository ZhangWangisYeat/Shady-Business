"""UCLA place search over the OpenStreetMap-derived catalog in ucla_places.json."""
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.places.osm_import import CATEGORY_RANK

CATALOG_FILE = Path(__file__).with_name("ucla_places.json")


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    coordinate: tuple[float, float]  # (longitude, latitude)
    category: str
    address: str | None = None
    aliases: tuple[str, ...] = ()


def normalize_text(text: str) -> str:
    # people type "charles e young" or "science & engineering", so punctuation and
    # "&" vs "and" shouldn't decide whether something matches.
    text = text.lower().replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_places() -> tuple[Place, ...]:
    return tuple(Place(p["id"], p["name"], (p["coordinate"][0], p["coordinate"][1]), p["category"],
                       p.get("address"), tuple(p.get("aliases", ()))) for p in _catalog()["places"])


def catalog_attribution() -> str:
    return _catalog()["metadata"]["attribution"]


def find_place(place_id: str) -> Place | None:
    return next((p for p in load_places() if p.id == place_id), None)


def match_score(place: Place, query: str) -> int | None:
    """Lower is better; None means no match."""
    name = normalize_text(place.name)
    words = name.split()
    tokens = query.split()
    others = [normalize_text(a) for a in place.aliases]
    if name.startswith(query):
        return 0
    if any(a == query or a.startswith(query) for a in others):
        return 1
    if all(any(w.startswith(t) for w in words) for t in tokens):
        return 2
    if query in name:
        return 3
    extra = " ".join(others + [normalize_text(place.address or ""), normalize_text(place.category)]).split()
    if all(any(w.startswith(t) for w in words + extra) for t in tokens):
        return 4
    return None


def search_places(query: str, limit: int = 8) -> list[Place]:
    normalized = normalize_text(query)
    ranked = []
    for place in load_places():
        score = 0 if not normalized else match_score(place, normalized)
        if score is not None:
            ranked.append((score, CATEGORY_RANK.get(place.category, 0), len(place.name), place.name, place))
    ranked.sort(key=lambda r: r[:4])
    return [r[-1] for r in ranked[:limit]]
