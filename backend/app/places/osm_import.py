"""Turn an Overpass `out center tags` response into the campus place catalog."""
import re
from math import cos, radians, sqrt

CAMPUS_CENTER = (-118.4452, 34.0689)
# the walking graph is downloaded 1400 m around the campus center, so anything
# further out than this can't snap to a path and the route call would just fail.
MAX_RADIUS_M = 1300.0

# these are named in OSM but nobody would walk "to" them (bus route relations,
# garden interpretive signs, creeks in culverts, bike counters and so on).
SKIP_TAGS = {
    "route": None, "type": {"route", "route_master"}, "waterway": None, "proposed": None,
    "aeroway": None, "barrier": None,
    "tourism": {"information"},
    "highway": {"bus_stop", "turning_circle", "platform"},
    "amenity": {"vending_machine", "parcel_locker", "loading_dock", "atm"},
    "man_made": {"monitoring_station"},
    "landuse": {"construction"},
    "place": None,
}

# first matching (key, value) wins, and value None means any value for that key.
CATEGORIES: list[tuple[str, str | None, str]] = [
    ("amenity", "library", "Library"),
    ("amenity", "cafe", "Café"),
    ("amenity", "fast_food", "Dining"), ("amenity", "restaurant", "Dining"), ("amenity", "food_court", "Dining"),
    ("amenity", "parking", "Parking"), ("building", "parking", "Parking"),
    ("amenity", "hospital", "Health"), ("amenity", "clinic", "Health"), ("amenity", "pharmacy", "Health"),
    ("building", "hospital", "Health"), ("healthcare", None, "Health"),
    ("building", "dormitory", "Housing"), ("building", "residential", "Housing"), ("building", "apartments", "Housing"),
    ("leisure", "stadium", "Athletics"), ("leisure", "sports_centre", "Athletics"), ("leisure", "pitch", "Athletics"),
    ("leisure", "track", "Athletics"), ("leisure", "swimming_pool", "Athletics"), ("landuse", "recreation_ground", "Athletics"),
    ("leisure", "garden", "Garden"), ("leisure", "park", "Plaza"), ("highway", "pedestrian", "Plaza"),
    ("tourism", "artwork", "Artwork"), ("historic", None, "Landmark"), ("amenity", "fountain", "Landmark"),
    ("tourism", "museum", "Museum"), ("tourism", "gallery", "Museum"),
    ("amenity", "theatre", "Venue"), ("amenity", "cinema", "Venue"), ("building", "auditorium", "Venue"),
    ("shop", None, "Shop"), ("amenity", "bank", "Bank"),
    ("highway", "footway", "Walkway"), ("highway", "steps", "Stairs"), ("highway", "cycleway", "Walkway"),
    ("highway", None, "Street"),
    ("building", None, "Building"), ("office", None, "Office"), ("amenity", None, "Place"), ("leisure", None, "Place"),
]

# lower sorts first, so typing "royce" offers Royce Hall before Royce Drive.
CATEGORY_RANK = {"Street": 3, "Walkway": 2, "Stairs": 2, "Artwork": 1}


def meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    return 111_320.0 * sqrt((a[1] - b[1]) ** 2 + ((a[0] - b[0]) * cos(radians((a[1] + b[1]) / 2))) ** 2)


def clean_text(text: str) -> str:
    # some OSM names have a broken en dash that came through as U+FFFD plus a
    # no-break space, and a few use ";" to join two names on one building.
    text = text.replace("�", "–").replace("\xa0", " ").replace(";", " / ")
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("&", "and")).strip("-")


def skipped(tags: dict) -> bool:
    for key, values in SKIP_TAGS.items():
        if key in tags and (values is None or tags[key] in values):
            return True
    # bus route relations carry a network/from tag but no feature tag at all
    return "network" in tags and "building" not in tags and "amenity" not in tags


def category(tags: dict) -> str | None:
    for key, value, label in CATEGORIES:
        if key in tags and (value is None or tags[key] == value):
            return label
    return None


def coordinate(element: dict) -> tuple[float, float] | None:
    if "lon" in element and "lat" in element:
        return (round(float(element["lon"]), 6), round(float(element["lat"]), 6))
    center = element.get("center")
    if center:
        return (round(float(center["lon"]), 6), round(float(center["lat"]), 6))
    return None


def address(tags: dict) -> str | None:
    street = tags.get("addr:street")
    if not street:
        return None
    number = tags.get("addr:housenumber")
    return clean_text(f"{number} {street}" if number else street)


def aliases(tags: dict) -> list[str]:
    found = []
    for key in ("short_name", "alt_name", "official_name", "old_name"):
        for value in tags.get(key, "").split(";"):
            value = clean_text(value)
            if value and value not in found:
                found.append(value)
    return found


def normalize(elements: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for element in elements:
        tags = element.get("tags", {})
        name = clean_text(tags.get("name", ""))
        point = coordinate(element)
        label = category(tags)
        if not name or point is None or label is None or skipped(tags):
            continue
        if meters(point, CAMPUS_CENTER) > MAX_RADIUS_M:
            continue
        groups.setdefault(name.lower(), []).append({
            "name": name, "coordinate": point, "category": label,
            "address": address(tags), "aliases": aliases(tags),
        })

    places = []
    for items in groups.values():
        # a long walkway like Bruin Walk comes back as many separate OSM ways, so
        # i keep the piece closest to the middle of all of them. and if the same
        # name is both a building and a street, the building is the better pin.
        best_rank = min(CATEGORY_RANK.get(i["category"], 0) for i in items)
        candidates = [i for i in items if CATEGORY_RANK.get(i["category"], 0) == best_rank]
        mid = (sum(i["coordinate"][0] for i in candidates) / len(candidates),
               sum(i["coordinate"][1] for i in candidates) / len(candidates))
        chosen = dict(min(candidates, key=lambda i: meters(i["coordinate"], mid)))
        chosen["aliases"] = sorted({a for i in items for a in i["aliases"]} - {chosen["name"]})
        chosen["address"] = chosen["address"] or next((i["address"] for i in items if i["address"]), None)
        places.append(chosen)

    places.sort(key=lambda p: p["name"].lower())
    used: dict[str, int] = {}
    for place in places:
        base = slugify(place["name"]) or "place"
        used[base] = used.get(base, 0) + 1
        place["id"] = base if used[base] == 1 else f"{base}-{used[base]}"
        place["coordinate"] = list(place["coordinate"])
    return [{k: p[k] for k in ("id", "name", "coordinate", "category", "address", "aliases")} for p in places]
