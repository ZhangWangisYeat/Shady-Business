"""Building and tree crown shadows in UCLA's local metric CRS.

No network calls or invented heights. Existing routing imports remain compatible;
the independent scoring module uses ``build_shadow_field`` for bounded coverage.
"""
import json
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime
from functools import lru_cache
from math import cos, isfinite, radians, sin, tan
from pathlib import Path
from typing import Literal, TYPE_CHECKING

from pyproj import Transformer
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from app.settings import SHADE_FILE, TREE_FILE

if TYPE_CHECKING:
    from app.shade.trees import TreeCrown

PROJECTION = Transformer.from_crs("EPSG:4326", "EPSG:26911", always_xy=True)
INVERSE_PROJECTION = Transformer.from_crs("EPSG:26911", "EPSG:4326", always_xy=True)
MIN_SOLAR_ELEVATION = 2.0
LIMITATIONS = (
    "Static departure-time obstruction shadow estimate on level terrain",
    "Clouds, terrain and sidewalk position are not modeled",
    "Sun classifications require explicitly verified obstruction coverage",
)


class ShadeDataUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ShadeModel:
    shapes: tuple[tuple[BaseGeometry, float], ...]
    data_as_of: str | None
    coverage_complete_verified: bool
    # Metric geometry inside which ALL relevant obstructions were checked.
    # A legacy boolean without a boundary cannot establish coverage anywhere.
    coverage_geometry: BaseGeometry | None = None
    source: str | None = None
    trees: tuple["TreeCrown", ...] = ()


@dataclass(frozen=True)
class ShadowField:
    shadows: BaseGeometry | None
    coverage_geometry: BaseGeometry | None
    status: Literal["daylight", "night", "low_sun", "unavailable"]
    data_as_of: str | None = None
    source: str | None = None
    limitations: tuple[str, ...] = LIMITATIONS
    # scoring keeps its lookup structures for this field here, so they are built
    # once per request instead of once per edge. not part of equality or hashing.
    cache: dict = dataclass_field(default_factory=dict, compare=False, hash=False, repr=False)


def model_coverage_status(model: ShadeModel | None) -> Literal["unavailable", "unverified", "verified"]:
    if model is None:
        return "unavailable"
    if (getattr(model, "coverage_complete_verified", False)
            and getattr(model, "coverage_geometry", None) is not None):
        return "verified"
    return "unverified"


def _project_polygon(geometry: dict) -> BaseGeometry:
    """Reject malformed, non-WGS84 and out-of-campus input, never repair silently."""
    polygon = shape(geometry)
    if polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid or polygon.has_z:
        raise ValueError("Expected a valid nonempty 2D Polygon or MultiPolygon")
    west, south, east, north = polygon.bounds
    if not (-118.49 <= west <= east <= -118.40 and 34.04 <= south <= north <= 34.10):
        raise ValueError("Shade geometry must use WGS84 [longitude, latitude] within UCLA service bounds")
    return transform(PROJECTION.transform, polygon)


def read_model(path: Path) -> ShadeModel | None:
    """Read a license-cleared building file; missing heights disable sun claims."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("type") != "FeatureCollection":
        raise ValueError("Building file must be a GeoJSON FeatureCollection")
    metadata = raw.get("metadata", {})
    coverage = metadata.get("coverage_geometry")
    coverage = _project_polygon(coverage) if coverage is not None else None
    buildings = []
    missing_height = False
    for feature in raw["features"]:
        polygon = _project_polygon(feature["geometry"])
        height = feature.get("properties", {}).get("height_m")
        if isinstance(height, bool) or not isinstance(height, (int, float)) or not isfinite(height) or not 1 <= height <= 250:
            missing_height = True
            continue
        buildings.append((polygon, float(height)))
    if not buildings and coverage is None:
        return None
    return ShadeModel(
        tuple(buildings), metadata.get("data_as_of"),
        metadata.get("coverage_complete_verified") is True and not missing_height,
        coverage, metadata.get("source"),
    )


@lru_cache(maxsize=1)
def load_model() -> ShadeModel | None:
    try:
        buildings = read_model(SHADE_FILE) if SHADE_FILE.is_file() else None
        return with_tree_file(buildings, TREE_FILE) if TREE_FILE.is_file() else buildings
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ShadeDataUnavailable("Shade dataset could not be loaded") from exc


def with_tree_file(buildings: ShadeModel | None, path: Path) -> ShadeModel | None:
    """Combine local sources without promoting incomplete coverage to sunshine."""
    from app.shade.trees import read_tree_model
    dataset = read_tree_model(path)
    if buildings is None and not dataset.trees:
        return None
    dates = [buildings.data_as_of if buildings else None, dataset.data_as_of]
    dates = dates if buildings else [dataset.data_as_of]
    source = "; ".join(s for s in (buildings.source if buildings else None, dataset.source) if s) or None
    coverage = None
    complete = bool(
        buildings and buildings.coverage_complete_verified and buildings.coverage_geometry is not None
        and dataset.coverage_complete_verified and dataset.coverage_geometry is not None
    )
    if complete:
        coverage = buildings.coverage_geometry.intersection(dataset.coverage_geometry)
        if coverage.is_empty:
            coverage, complete = None, False
    return ShadeModel(
        buildings.shapes if buildings else (),
        dates[0] if all(d is not None and d == dates[0] for d in dates) else None,
        complete, coverage, source, dataset.trees,
    )


def cast_shadow(base: BaseGeometry, height_m: float, elevation_deg: float, azimuth_deg: float) -> BaseGeometry:
    """Sweep a footprint away from the sun without filling concavities/courtyards.

    Inputs are projected meters; azimuth is clockwise from true north.
    At unreliable solar angles the caller must return unknown, not cap the reach.
    """
    if not all(isfinite(x) for x in (height_m, elevation_deg, azimuth_deg)) or height_m <= 0:
        raise ValueError("Height must be positive and solar angles must be finite")
    if not MIN_SOLAR_ELEVATION < elevation_deg <= 90:
        raise ValueError("Solar elevation must be greater than 2 and at most 90 degrees")
    if base.geom_type not in ("Polygon", "MultiPolygon") or base.is_empty or not base.is_valid or base.has_z:
        raise ValueError("Footprint must be a valid nonempty 2D Polygon or MultiPolygon in meters")
    distance = height_m / tan(radians(elevation_deg))
    dx = -distance * sin(radians(azimuth_deg))
    dy = -distance * cos(radians(azimuth_deg))
    if distance < 1e-9:
        return base
    parts = [base, translate(base, xoff=dx, yoff=dy)]
    for polygon in base.geoms if base.geom_type == "MultiPolygon" else (base,):
        for ring in (polygon.exterior, *polygon.interiors):
            for a, b in zip(ring.coords, list(ring.coords)[1:]):
                wall = Polygon([a, b, (b[0] + dx, b[1] + dy), (a[0] + dx, a[1] + dy)])
                if wall.area > 0:
                    parts.append(wall)
    return unary_union(parts)


def solar_angles(when: datetime) -> tuple[float, float]:
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("Departure time must include a timezone offset")
    from astral import Observer
    from astral.sun import azimuth, elevation
    observer = Observer(latitude=34.0689, longitude=-118.4452)
    return elevation(observer, when, with_refraction=False), azimuth(observer, when)


def build_shadow_field(model: ShadeModel | None, when: datetime, area: BaseGeometry | None = None) -> ShadowField:
    elevation_deg, azimuth_deg = solar_angles(when)
    limitations = LIMITATIONS + ((
        "Tree crowns are opaque ellipsoids; foliage transmission and field accuracy are unverified",
        "Crown vertical extent is assumed where inventory crown base height is absent",
    ) if model and model.trees else ("Tree shade is not modeled without usable inventory dimensions",))
    info = dict(data_as_of=model.data_as_of if model else None, source=model.source if model else None,
                limitations=limitations)
    if elevation_deg <= 0:
        return ShadowField(None, None, "night", **info)
    if elevation_deg <= MIN_SOLAR_ELEVATION:
        return ShadowField(None, None, "low_sun", **info)
    if model is None:
        return ShadowField(None, None, "unavailable", **info)
    from app.shade.trees import cast_tree_shadow
    shapes, trees = model.shapes, model.trees
    coverage = model.coverage_geometry if model.coverage_complete_verified else None
    if area is not None:
        # once the dataset covered the whole campus (25k+ trees), unioning every
        # shadow took 10-20 s per request even though a walk only ever touches a
        # few walkways. so an obstacle is only cast when its own shadow could
        # reach the area: at this sun angle something h meters tall throws its
        # shadow at most h / tan(elevation) away (plus its crown or footprint
        # size), so anything further out can't change a single walkway. the
        # area can be lines (the walkways themselves). the field is then only
        # right on those lines, so it must only be asked about them, and a
        # polygon area also cuts the coverage so nothing outside reads as sunny
        # just because its shadows were skipped.
        import numpy as np
        import shapely
        cotangent = 1 / tan(radians(elevation_deg))
        shapely.prepare(area)
        if shapes:
            reach = np.array([height * cotangent + 5 for _, height in shapes])
            keep = shapely.dwithin(np.array([base for base, _ in shapes], dtype=object), area, reach)
            shapes = tuple(item for item, kept in zip(shapes, keep) if kept)
        if trees:
            reach = np.array([t.height_m * cotangent + 2 * t.crown_radius_m + 5 for t in trees])
            keep = shapely.dwithin(np.array([t.center for t in trees], dtype=object), area, reach)
            trees = tuple(t for t, kept in zip(trees, keep) if kept)
        if coverage is not None and area.geom_type in ("Polygon", "MultiPolygon"):
            coverage = coverage.intersection(area)
            if coverage.is_empty:
                coverage = None
    parts = [cast_shadow(base, height, elevation_deg, azimuth_deg) for base, height in shapes]
    parts.extend(cast_tree_shadow(tree, elevation_deg, azimuth_deg) for tree in trees)
    shadows = unary_union(parts)
    return ShadowField(shadows, coverage, "daylight", **info)


def shadow_polygons(model: ShadeModel, when: datetime):
    """Compatibility entry point for the existing routing service."""
    field = build_shadow_field(model, when)
    return field.shadows if field.status == "daylight" else None


def fraction_sun(shadows, coords: list[tuple[float, float]], n: int = 9) -> float | None:
    """Legacy geometric fraction, now exact; ``n`` retained for call compatibility.

    This alone does NOT establish sun/unknown coverage. Use scoring.score_route
    for coverage-aware exposure. Count repeated traversals separately.
    """
    if shadows is None:
        return None
    line = transform(PROJECTION.transform, LineString(coords))
    length = line.length
    if length < .01:
        return None
    covered = sum(LineString([a, b]).intersection(shadows).length for a, b in zip(line.coords, list(line.coords)[1:]))
    return max(0.0, min(1.0, 1 - covered / length))
