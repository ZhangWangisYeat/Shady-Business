"""Initial campus landmark search. Coordinates require field validation before release."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Place:
    id: str
    name: str
    coordinate: tuple[float, float]  # (longitude, latitude)

PLACES: tuple[Place, ...] = (
    Place("royce-hall", "Royce Hall", (-118.4422, 34.0728)),
    Place("powell-library", "Powell Library", (-118.4418, 34.0716)),
    Place("ackerman-union", "Ackerman Union", (-118.4440, 34.0703)),
    Place("bruin-plaza", "Bruin Plaza", (-118.4445, 34.0709)),
    Place("engineering-vi", "Engineering VI", (-118.4446, 34.0681)),
)


def find_place(place_id: str) -> Place | None:
    return next((p for p in PLACES if p.id == place_id), None)


def search_places(query: str) -> list[Place]:
    normalized = query.lower().strip()
    return [p for p in PLACES if normalized in p.name.lower() or normalized in p.id][:10]
