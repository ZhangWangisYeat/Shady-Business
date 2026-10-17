from app.routing.directions import Leg, build_steps, first_value, maneuver_for, turn_angle

# roughly 1 m in degrees at UCLA's latitude, so the synthetic legs read in meters
LAT = 1 / 111_320
LON = 1 / (111_320 * 0.8283)
O = (-118.4450, 34.0700)


def at(east_m, north_m):
    return (O[0] + east_m * LON, O[1] + north_m * LAT)


def leg(points, name=None, highway="footway"):
    coords = [at(*p) for p in points]
    length = sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(points, points[1:]))
    return Leg(coords, length, name, highway)


def test_turn_angle_sign_and_maneuvers():
    assert turn_angle(0, 90) == 90 and turn_angle(0, 270) == -90 and turn_angle(350, 10) == 20
    assert maneuver_for(10) == "straight" and maneuver_for(-45) == "slight_left"
    assert maneuver_for(90) == "right" and maneuver_for(-170) == "sharp_left"


def test_north_then_left_onto_named_walk():
    steps = build_steps([
        leg([(0, 0), (0, 60)]),
        leg([(0, 60), (0, 120)]),
        leg([(0, 120), (-80, 120)], name="Bruin Walk"),
    ])
    assert [s["maneuver"] for s in steps] == ["depart", "left", "arrive"]
    assert steps[0]["instruction"] == "Head north on the walkway"
    assert steps[0]["distance_m"] == 120.0
    assert steps[1]["instruction"] == "Turn left onto Bruin Walk" and steps[1]["way_name"] == "Bruin Walk"


def test_tiny_crosswalk_folds_away():
    steps = build_steps([
        leg([(0, 0), (0, 50)], name="Bruin Walk"),
        leg([(0, 50), (6, 50)]),
        leg([(6, 50), (6, 110)], name="Bruin Walk"),
    ])
    assert [s["maneuver"] for s in steps] == ["depart", "arrive"]
    assert steps[0]["distance_m"] == 116.0


def test_stairs_label_and_graphml_list_names():
    assert first_value("['Janss Steps', 'Bruin Walk']") == "Janss Steps"
    steps = build_steps([leg([(0, 0), (0, 40)]), leg([(0, 40), (40, 40)], highway="['steps', 'footway']")])
    assert steps[1]["instruction"] == "Turn right onto the stairs"


def test_empty_path():
    assert build_steps([]) == []
