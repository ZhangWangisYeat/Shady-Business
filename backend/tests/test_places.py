from app.places.catalog import Place, find_place, match_score, normalize_text, search_places
from app.places.osm_import import normalize


def ids(query, limit=8):
    return [p.id for p in search_places(query, limit)]


def test_building_beats_street_with_same_prefix():
    assert ids("royce")[:2] == ["royce-hall", "royce-drive"]


def test_alias_and_word_prefix_matching():
    assert "bruin-plate" in ids("bplate")
    assert ids("young research")[0] == "charles-e-young-research-library"
    assert "powell-library" in ids("POWELL lib")


def test_punctuation_and_ampersand_do_not_block_matches():
    assert normalize_text("Science & Engineering") == "science and engineering"
    place = Place("x", "Charles E. Young Research Library", (-118.44, 34.07), "Library")
    assert match_score(place, normalize_text("charles e young")) == 0


def test_no_match_and_limit():
    assert search_places("zzzz-not-a-place") == []
    assert len(search_places("", 5)) == 5


def test_catalog_places_are_inside_campus_service_bounds():
    for place in search_places("", 1000):
        lon, lat = place.coordinate
        assert -118.49 <= lon <= -118.40 and 34.04 <= lat <= 34.10
    assert find_place("ackerman-union").name == "Ackerman Union"


def test_osm_normalize_dedupes_skips_and_slugs():
    elements = [
        {"type": "way", "center": {"lon": -118.4422, "lat": 34.0729}, "tags": {"name": "Royce Hall", "building": "university"}},
        {"type": "way", "center": {"lon": -118.4425, "lat": 34.0749}, "tags": {"name": "Royce Drive", "highway": "service"}},
        {"type": "way", "center": {"lon": -118.4460, "lat": 34.0705}, "tags": {"name": "Bruin Walk", "highway": "footway"}},
        {"type": "way", "center": {"lon": -118.4450, "lat": 34.0708}, "tags": {"name": "Bruin Walk", "highway": "footway"}},
        {"type": "way", "center": {"lon": -118.4440, "lat": 34.0711}, "tags": {"name": "Bruin Walk", "highway": "footway"}},
        {"type": "node", "lon": -118.4430, "lat": 34.0700, "tags": {"name": "Bromeliads", "tourism": "information"}},
        {"type": "relation", "tags": {"name": "U1 Weyburn", "network": "BruinBus", "from": "x"}},
        {"type": "node", "lon": -118.30, "lat": 34.07, "tags": {"name": "Far Away Hall", "building": "yes"}},
        {"type": "node", "lon": -118.4440, "lat": 34.0703, "tags": {"name": "Caf�\xa0Med", "amenity": "cafe", "short_name": "CM"}},
    ]
    places = {p["id"]: p for p in normalize(elements)}
    assert set(places) == {"royce-hall", "royce-drive", "bruin-walk", "caf-med"}
    # the middle piece of a multi-way walkway is the pin
    assert places["bruin-walk"]["coordinate"] == [-118.445, 34.0708]
    assert places["royce-drive"]["category"] == "Street"
    assert places["caf-med"]["name"] == "Caf– Med" and places["caf-med"]["aliases"] == ["CM"]


def test_attach_addresses_inside_nearby_and_skipped():
    from app.places.osm_import import attach_addresses
    lat_m, lon_m = 1 / 111_320, 1 / (111_320 * 0.8283)
    def at(east, north):
        return [-118.4452 + east * lon_m, 34.0689 + north * lat_m]
    def ring(e0, n0, e1, n1):
        return [dict(zip(("lon", "lat"), at(e, n))) for e, n in [(e0, n0), (e1, n0), (e1, n1), (e0, n1), (e0, n0)]]
    elements = [
        {"type": "way", "tags": {"addr:housenumber": "308", "addr:street": "Westwood Plaza"}, "geometry": ring(0, 0, 40, 40)},
        {"type": "node", "lon": at(200, 0)[0], "lat": at(200, 0)[1], "tags": {"addr:housenumber": "520", "addr:street": "Portola Plaza"}},
    ]
    places = [
        {"name": "Cafe inside", "category": "Café", "coordinate": at(20, 20), "address": None},
        {"name": "Hall 10 m away", "category": "Building", "coordinate": at(210, 0), "address": None},
        {"name": "Hall 25 m away", "category": "Building", "coordinate": at(225, 0), "address": None},
        {"name": "Statue next door", "category": "Artwork", "coordinate": at(205, 0), "address": None},
        {"name": "Walk through it", "category": "Walkway", "coordinate": at(20, 20), "address": None},
        {"name": "Has its own", "category": "Building", "coordinate": at(20, 20), "address": "1 Own St"},
    ]
    assert attach_addresses(places, elements) == 2
    assert [p["address"] for p in places] == ["308 Westwood Plaza", "520 Portola Plaza", None, None, None, "1 Own St"]


def test_catalog_has_filled_addresses():
    assert find_place("ackerman-union").address == "308 Westwood Plaza"
