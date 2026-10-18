"""Find the places our routes use where the tree inventory says little or nothing."""
from dataclasses import asdict, dataclass

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from app.vision.geo import local_xy, meters_between

ORIGIN = (-118.4452, 34.0689)  # campus center, just a reference for local meters


@dataclass
class GapSite:
    id: str
    name: str
    coordinate: tuple[float, float]
    # outside_inventory: the inventory never covered this ground at all, so no
    # trees means "unknown", not "no trees". sparse_inventory: inside coverage
    # but almost nothing recorded nearby, which is worth a second look.
    reason: str
    trees_nearby: int
    place_ids: list[str]

    def to_json(self) -> dict:
        return asdict(self)


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def find_gap_sites(places: list[dict], tree_points: list[tuple[float, float]], coverage: BaseGeometry | None,
                   *, radius_m: float = 80, sparse_max: int = 2, merge_m: float = 120,
                   focus: list[str] = (), limit: int | None = None) -> list[GapSite]:
    """Route places with no inventory trees around them, merged into sites.

    Places closer than merge_m share one site, because photos of one spot
    cover its neighbours too, and the photo and gemini budgets are small.
    Sites with more route places come first; anything named in focus jumps the
    queue.
    """
    points = [Point(*local_xy(lon, lat, ORIGIN)) for lon, lat in tree_points]
    tree = STRtree(points) if points else None
    gaps = []
    for place in places:
        lon, lat = place["coordinate"]
        here = Point(*local_xy(lon, lat, ORIGIN))
        nearby = len(tree.query(here.buffer(radius_m), predicate="intersects")) if tree is not None else 0
        covered = coverage is not None and coverage.contains(Point(lon, lat))
        if not covered:
            gaps.append((place, "outside_inventory", nearby))
        elif nearby <= sparse_max:
            gaps.append((place, "sparse_inventory", nearby))

    wanted = [f.lower() for f in focus]
    def priority(item):
        place = item[0]
        return (not any(w in place["name"].lower() for w in wanted), place["name"])
    sites: list[GapSite] = []
    for place, reason, nearby in sorted(gaps, key=priority):
        coordinate = tuple(place["coordinate"])
        home = next((s for s in sites if meters_between(s.coordinate, coordinate) <= merge_m), None)
        if home:
            home.place_ids.append(place["id"])
            continue
        sites.append(GapSite(_slug(place["name"]), place["name"], coordinate, reason, nearby, [place["id"]]))
    focused = [s for s in sites if any(w in s.name.lower() for w in wanted)]
    rest = sorted((s for s in sites if s not in focused), key=lambda s: -len(s.place_ids))
    ordered = focused + rest
    return ordered[:limit] if limit else ordered


def sample_route(coordinates: list[tuple[float, float]], coverage: BaseGeometry | None, every_m: float = 90,
                 name: str = "route") -> list[GapSite]:
    """Points every every_m along a walk that fall outside inventory coverage.

    This is for "the path from Olympic Hall to here": the gap isn't only the
    destination, it's every stretch of walkway on the way.
    """
    sites, walked, next_at = [], 0.0, 0.0
    for a, b in zip(coordinates, coordinates[1:]):
        length = meters_between(a, b)
        while length and next_at <= walked + length:
            t = (next_at - walked) / length
            point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if coverage is None or not coverage.contains(Point(point)):
                sites.append(GapSite(f"{_slug(name)}-{len(sites) + 1}", f"{name} ({int(next_at)} m)", point,
                                     "outside_inventory", 0, []))
            next_at += every_m
        walked += length
    return sites


def coverage_of(tree_file: dict) -> BaseGeometry | None:
    geometry = (tree_file.get("metadata") or {}).get("coverage_geometry")
    return shape(geometry) if geometry else None
