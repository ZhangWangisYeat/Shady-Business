"""Turn a path of walking-graph edges into readable step-by-step directions."""
import ast
from dataclasses import dataclass, field
from math import atan2, cos, degrees, radians

Coord = tuple[float, float]

# below these turn angles (degrees) a bend counts as going straight / a slight turn.
# campus footways wiggle a lot, so anything under 35 degrees reads as "continue".
STRAIGHT_DEG = 35.0
TURN_DEG = 60.0
SHARP_DEG = 140.0
# legs shorter than this (crosswalk stubs, tiny connectors) get folded into the
# step before them, otherwise you'd see "turn left, walk 3 m, turn right" noise.
MIN_STEP_M = 15.0
# measure a leg's heading over its first/last ~12 m instead of the very first
# vertex pair, which is often a one meter jog that points the wrong way.
BEARING_SAMPLE_M = 12.0

WAY_LABELS = {
    "steps": "the stairs", "footway": "the walkway", "path": "the path", "pedestrian": "the plaza",
    "corridor": "the corridor", "elevator": "the elevator", "cycleway": "the path", "track": "the path",
    "service": "the service road", "living_street": "the street",
}


@dataclass(frozen=True)
class Leg:
    coords: list[Coord]
    length_m: float
    name: str | None
    highway: str | None


@dataclass
class Step:
    maneuver: str
    way: str
    named: bool
    distance_m: float
    start_bearing: float = 0.0
    exit_bearing: float = 0.0
    legs: list[Leg] = field(default_factory=list)


def first_value(raw) -> str | None:
    # osmnx joins merged ways into a list, and graphml stores that list as the
    # string "['Bruin Walk', 'Janss Steps']", so i take the first entry.
    if raw is None:
        return None
    if isinstance(raw, list):
        return str(raw[0]) if raw else None
    text = str(raw).strip()
    if text.startswith("["):
        try:
            values = ast.literal_eval(text)
            return str(values[0]) if values else None
        except (ValueError, SyntaxError):
            return None
    return text or None


def way_label(leg: Leg) -> tuple[str, bool]:
    name = first_value(leg.name)
    if name:
        return name, True
    return WAY_LABELS.get(first_value(leg.highway) or "", "the street"), False


def _xy(a: Coord, b: Coord) -> tuple[float, float]:
    mid = cos(radians((a[1] + b[1]) / 2))
    return (b[0] - a[0]) * 111_320.0 * mid, (b[1] - a[1]) * 111_320.0


def bearing(a: Coord, b: Coord) -> float:
    dx, dy = _xy(a, b)
    return (degrees(atan2(dx, dy)) + 360.0) % 360.0


def _sample(coords: list[Coord]) -> Coord:
    walked = 0.0
    for a, b in zip(coords, coords[1:]):
        dx, dy = _xy(a, b)
        walked += (dx * dx + dy * dy) ** 0.5
        if walked >= BEARING_SAMPLE_M:
            return b
    return coords[-1]


def start_bearing(leg: Leg) -> float:
    return bearing(leg.coords[0], _sample(leg.coords))


def end_bearing(leg: Leg) -> float:
    reverse = list(reversed(leg.coords))
    return bearing(_sample(reverse), reverse[0])


def turn_angle(before: float, after: float) -> float:
    """Signed change in heading, positive means turning right."""
    return (after - before + 540.0) % 360.0 - 180.0


def maneuver_for(angle: float) -> str:
    size = abs(angle)
    if size < STRAIGHT_DEG:
        return "straight"
    side = "right" if angle > 0 else "left"
    if size < TURN_DEG:
        return f"slight_{side}"
    if size < SHARP_DEG:
        return side
    return f"sharp_{side}"


def compass(degrees_from_north: float) -> str:
    names = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
    return names[int(((degrees_from_north + 22.5) % 360) // 45)]


def instruction(step: Step, previous_way: str | None) -> str:
    on = step.way
    if step.maneuver == "depart":
        return f"Head {compass(step.start_bearing)} on {on}"
    if step.maneuver == "arrive":
        return "Arrive at your destination"
    if step.maneuver == "straight":
        return f"Continue onto {on}" if on != previous_way else f"Continue on {on}"
    verb = {"slight_left": "Bear left", "slight_right": "Bear right", "left": "Turn left", "right": "Turn right",
            "sharp_left": "Turn sharply left", "sharp_right": "Turn sharply right"}[step.maneuver]
    if on != previous_way:
        return f"{verb} onto {on}"
    # "turn left to stay on the walkway" over and over is just noise when most
    # campus paths have no name, so unnamed ones get the bare turn.
    return f"{verb} to stay on {on}" if step.named else verb


def build_steps(legs: list[Leg]) -> list[dict]:
    legs = [leg for leg in legs if len(leg.coords) >= 2]
    if not legs:
        return []
    steps: list[Step] = []
    for leg in legs:
        way, named = way_label(leg)
        if not steps:
            steps.append(Step("depart", way, named, leg.length_m, start_bearing(leg), end_bearing(leg), [leg]))
            continue
        current = steps[-1]
        move = maneuver_for(turn_angle(current.exit_bearing, start_bearing(leg)))
        if way == current.way and move == "straight":
            current.legs.append(leg)
            current.distance_m += leg.length_m
            current.exit_bearing = end_bearing(leg)
        else:
            steps.append(Step(move, way, named, leg.length_m, start_bearing(leg), end_bearing(leg), [leg]))

    # fold short steps into the one before. the folded step's heading is thrown
    # away on purpose, so the next turn is measured from where you were really
    # walking (Bruin Walk, 6 m crosswalk jog, Bruin Walk reads as one straight walk).
    tidy: list[Step] = [steps[0]]
    for step in steps[1:]:
        last = tidy[-1]
        if step.distance_m < MIN_STEP_M:
            last.distance_m += step.distance_m
            last.legs.extend(step.legs)
            continue
        step.maneuver = maneuver_for(turn_angle(last.exit_bearing, step.start_bearing))
        if step.way == last.way and step.maneuver == "straight":
            last.distance_m += step.distance_m
            last.legs.extend(step.legs)
            last.exit_bearing = step.exit_bearing
        else:
            tidy.append(step)

    result = []
    previous_way = None
    for step in tidy:
        result.append({"maneuver": step.maneuver, "instruction": instruction(step, previous_way),
                       "way_name": step.way if step.named else None, "distance_m": round(step.distance_m, 1)})
        previous_way = step.way
    result.append({"maneuver": "arrive", "instruction": "Arrive at your destination", "way_name": None, "distance_m": 0.0})
    return result
