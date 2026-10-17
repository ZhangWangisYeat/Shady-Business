#!/usr/bin/env python3
"""Build backend/app/places/ucla_places.json from named OpenStreetMap features on the UCLA campus."""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.places.osm_import import normalize  # noqa: E402

OUTPUT = ROOT / "backend/app/places/ucla_places.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
# the campus boundary polygon in OSM, so we don't pull in Westwood Village shops
# or Bel Air houses that just happen to sit inside a bounding box.
QUERY = """[out:json][timeout:60];
area["amenity"="university"]["name"="University of California, Los Angeles"]->.ucla;
nwr(area.ucla)["name"];
out center tags;"""


def fetch() -> list[dict]:
    import requests
    for attempt in range(2):
        response = requests.post(OVERPASS, data={"data": QUERY}, timeout=90,
                                 headers={"User-Agent": "shady-business-dev/0.1"})
        if response.ok:
            return response.json()["elements"]
        # overpass hands out 429/502/504 when it's busy, so one polite retry is
        # worth it but hammering it isn't.
        print(f"Overpass returned {response.status_code}", file=sys.stderr)
        if attempt == 0:
            time.sleep(15)
    raise SystemExit("Overpass unavailable; try again later")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-network", action="store_true", help="I authorize one free OSM Overpass request")
    parser.add_argument("--input", type=Path, help="normalize a saved Overpass JSON response instead of fetching")
    args = parser.parse_args()
    if args.input:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        elements = raw["elements"] if isinstance(raw, dict) else raw
    elif args.confirm_network:
        elements = fetch()
    else:
        parser.error("pass --confirm-network to contact Overpass, or --input with a saved response")

    places = normalize(elements)
    catalog = {
        "metadata": {
            "source": "OpenStreetMap features inside the UCLA campus boundary (Overpass API)",
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "data_as_of": date.today().isoformat(),
            "coordinate_note": "building/area centers; not verified entrance points",
        },
        "places": places,
    }
    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Saved {len(places)} places from {len(elements)} OSM features: {OUTPUT}")


if __name__ == "__main__":
    main()
