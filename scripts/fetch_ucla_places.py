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
from app.places.osm_import import attach_addresses, normalize  # noqa: E402

OUTPUT = ROOT / "backend/app/places/ucla_places.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
# the campus boundary polygon in OSM, so we don't pull in Westwood Village shops
# or Bel Air houses that just happen to sit inside a bounding box.
QUERY = """[out:json][timeout:60];
area["amenity"="university"]["name"="University of California, Los Angeles"]->.ucla;
nwr(area.ucla)["name"];
out center tags;"""
# separate query because containment needs the full building outlines, and
# asking for geometry on all 650 named features would be a much bigger download.
ADDRESS_QUERY = """[out:json][timeout:60];
area["amenity"="university"]["name"="University of California, Los Angeles"]->.ucla;
nwr(area.ucla)["addr:housenumber"]["addr:street"];
out tags geom;"""


def fetch(query: str) -> list[dict]:
    import requests
    for attempt in range(2):
        response = requests.post(OVERPASS, data={"data": query}, timeout=90,
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
    parser.add_argument("--address-input", type=Path, help="saved response of ADDRESS_QUERY to use with --input")
    args = parser.parse_args()
    def load(path: Path) -> list[dict]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw["elements"] if isinstance(raw, dict) else raw

    if args.input:
        elements = load(args.input)
        address_elements = load(args.address_input) if args.address_input else []
    elif args.confirm_network:
        elements = fetch(QUERY)
        time.sleep(5)
        address_elements = fetch(ADDRESS_QUERY)
    else:
        parser.error("pass --confirm-network to contact Overpass, or --input with a saved response")

    places = normalize(elements)
    added = attach_addresses(places, address_elements)
    catalog = {
        "metadata": {
            "source": "OpenStreetMap features inside the UCLA campus boundary (Overpass API)",
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "data_as_of": date.today().isoformat(),
            "coordinate_note": "building/area centers; not verified entrance points",
            "address_note": "the place's own OSM address, else the addressed OSM building it sits inside, else an addressed OSM feature within 15 m (not for artwork, gardens, plazas or streets)",
        },
        "places": places,
    }
    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with_address = sum(1 for p in places if p["address"])
    print(f"Saved {len(places)} places from {len(elements)} OSM features ({with_address} with an address, {added} filled from nearby buildings): {OUTPUT}")


if __name__ == "__main__":
    main()
