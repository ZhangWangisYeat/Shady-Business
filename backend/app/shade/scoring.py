"""Pure, provider-independent route exposure scoring, without API schema changes.

Split each straight road piece at every shade/coverage boundary, classify its
interior, and apportion supplied walking time by projected distance. Iterating
original pieces preserves route order and repeated traversal of the same path.
"""
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Iterable, Literal

import shapely
from shapely.geometry import LineString, Point, mapping
from shapely.strtree import STRtree
from shapely.ops import transform

from app.shade.model import INVERSE_PROJECTION, PROJECTION, ShadowField

State = Literal["shade", "sun", "unknown", "no_direct_sun"]


@dataclass(frozen=True)
class RouteEdge:
    coordinates: tuple[tuple[float, float], ...]  # WGS84 [longitude, latitude]
    duration_s: float  # From routing provider; never inferred from shade


@dataclass(frozen=True)
class ScoredSegment:
    shade_state: State
    distance_m: float
    duration_s: float
    sun_seconds: float | None
    unknown_seconds: float
    geometry: dict


@dataclass(frozen=True)
class RouteShadeScore:
    distance_m: float
    duration_s: float
    shade_seconds: float
    known_sun_seconds: float
    unknown_seconds: float
    no_direct_sun_seconds: float
    sun_seconds: float | None  # Complete total only; null if any exposure unknown
    sun_seconds_min: float
    sun_seconds_max: float
    shade_fraction: float | None  # Distance fraction; null if incomplete or night
    known_fraction: float  # Fraction of walking time whose state is modeled
    model_status: str
    data_as_of: str | None
    source: str | None
    limitations: tuple[str, ...]
    segments: tuple[ScoredSegment, ...]

    def to_dict(self) -> dict:
        """JSON-serializable internal result, not a new public HTTP contract."""
        return asdict(self)


def _coordinates(geometry):
    """Yield boundary intersection vertices, including collinear overlaps."""
    if geometry.is_empty:
        return
    if geometry.geom_type in ("Point", "LineString", "LinearRing"):
        yield from geometry.coords
    else:
        for part in geometry.geoms:
            yield from _coordinates(part)


def _outlines(field: ShadowField):
    """Spatial index over the shadow and coverage outlines, built once per field.

    Rebuilding ``area.boundary`` for every edge and intersecting each piece with
    the whole campus outline was most of the routing time. Intersecting with the
    individual outline rings near a piece gives the same cut points.
    """
    if "outlines" not in field.cache:
        parts = []
        for area in (field.shadows, field.coverage_geometry):
            if area is not None and not area.is_empty:
                # prepared geometry makes the covers() checks in _state faster
                shapely.prepare(area)
                parts.extend(shapely.get_parts(area.boundary))
        field.cache["outlines"] = (STRtree(parts) if parts else None, parts)
    return field.cache["outlines"]


def _state(field: ShadowField, point: Point) -> State:
    if field.status == "night":
        return "no_direct_sun"
    if field.status != "daylight" or field.shadows is None:
        return "unknown"
    if field.shadows.covers(point):
        return "shade"
    if field.coverage_geometry is not None and field.coverage_geometry.covers(point):
        return "sun"
    return "unknown"


def score_route(edges: Iterable[RouteEdge], field: ShadowField) -> RouteShadeScore:
    """Score connected edges at one static timestamp using metric intersection.

    Shade inside a known obstacle shadow can be modeled even with incomplete
    surroundings. Its complement is sun ONLY inside explicit verified coverage.
    Supplied coverage must account for obstacles outside its boundary that can
    cast shadows inward. Empty/zero-length routes are rejected, not 100% shaded.
    """
    raw_segments = []
    total_distance = total_duration = 0.0
    seconds = dict.fromkeys(("shade", "sun", "unknown", "no_direct_sun"), 0.0)
    previous_end = None
    tree, outline_parts = _outlines(field) if field.status == "daylight" else (None, ())
    for edge in edges:
        if isinstance(edge.duration_s, bool) or not isfinite(edge.duration_s) or edge.duration_s <= 0:
            raise ValueError("Edge duration_s must be finite and greater than zero")
        if len(edge.coordinates) < 2:
            raise ValueError("Each edge requires at least two WGS84 coordinates")
        for coordinate in edge.coordinates:
            if len(coordinate) != 2:
                raise ValueError("Coordinates must be WGS84 [longitude, latitude]")
            lon, lat = coordinate
            if not all(isfinite(x) for x in coordinate) or not (-118.49 <= lon <= -118.40 and 34.04 <= lat <= 34.10):
                raise ValueError("Coordinates must be within UCLA service bounds in WGS84 [longitude, latitude]")
        projected = transform(PROJECTION.transform, LineString(edge.coordinates))
        if projected.length < .01:
            raise ValueError("Edge must have at least 0.01 meters of geometry")
        if previous_end is not None and previous_end.distance(Point(projected.coords[0])) > 1e-5:
            raise ValueError("Route edges must connect in traversal order")
        previous_end = Point(projected.coords[-1])
        total_distance += projected.length
        total_duration += edge.duration_s
        edge_start = len(raw_segments)
        # Set operations on a whole line can collapse repeated traversals.
        for a, b in zip(projected.coords, list(projected.coords)[1:]):
            piece = LineString([a, b])
            if piece.length == 0:
                continue
            cuts = {0.0, piece.length}
            if tree is not None:
                for i in tree.query(piece, predicate="intersects"):
                    cuts.update(piece.project(Point(c)) for c in _coordinates(piece.intersection(outline_parts[i])))
            ordered = sorted(cuts)
            for start, end in zip(ordered, ordered[1:]):
                if end <= start:
                    continue
                state = _state(field, piece.interpolate((start + end) / 2))
                distance = end - start
                duration = edge.duration_s * distance / projected.length
                seconds[state] += duration
                coordinates = [piece.interpolate(start).coords[0], piece.interpolate(end).coords[0]]
                # Preserve vertices/loops when merging adjacent equal states.
                if len(raw_segments) > edge_start and raw_segments[-1][0] == state:
                    last = raw_segments[-1]
                    if last[3][-1] != coordinates[0]:
                        last[3].append(coordinates[0])
                    last[3].append(coordinates[1])
                    last[1] += distance
                    last[2] += duration
                else:
                    raw_segments.append([state, distance, duration, coordinates])
    if not raw_segments:
        raise ValueError("Route must contain at least one nonzero-length edge")
    segments = tuple(
        ScoredSegment(state, distance, duration,
                      None if state == "unknown" else duration if state == "sun" else 0.0,
                      duration if state == "unknown" else 0.0,
                      mapping(transform(INVERSE_PROJECTION.transform, LineString(coords))))
        for state, distance, duration, coords in raw_segments
    )
    unknown = seconds["unknown"]
    return RouteShadeScore(
        distance_m=total_distance, duration_s=total_duration,
        shade_seconds=seconds["shade"], known_sun_seconds=seconds["sun"],
        unknown_seconds=unknown, no_direct_sun_seconds=seconds["no_direct_sun"],
        sun_seconds=None if unknown > 0 else seconds["sun"],
        sun_seconds_min=seconds["sun"], sun_seconds_max=seconds["sun"] + unknown,
        shade_fraction=sum(s.distance_m for s in segments if s.shade_state == "shade") / total_distance
        if unknown == 0 and field.status == "daylight" else None,
        known_fraction=max(0.0, min(1.0, 1 - unknown / total_duration)),
        model_status=field.status, data_as_of=field.data_as_of, source=field.source,
        limitations=field.limitations, segments=segments,
    )
