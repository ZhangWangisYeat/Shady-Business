"""Measured tree dimensions with an explicitly approximate opaque crown model."""
from dataclasses import dataclass
import json
from math import cos, isfinite, pi, radians, sin, sqrt, tan
from pathlib import Path

from shapely.affinity import rotate, scale, translate
from shapely.geometry import Point, Polygon, shape
from shapely.geometry.base import BaseGeometry

from app.shade.model import MIN_SOLAR_ELEVATION, PROJECTION, _project_polygon


@dataclass(frozen=True)
class TreeCrown:
    center: Point  # Projected meters, not latitude/longitude
    height_m: float  # Inventory total height
    crown_radius_m: float  # Half inventory horizontal crown spread
    tree_id: str
    crown_base_m: float | None = None


@dataclass(frozen=True)
class TreeDataset:
    trees: tuple[TreeCrown, ...]
    source: str | None
    data_as_of: str | None
    unmodeled_records: int
    coverage_complete_verified: bool
    coverage_geometry: BaseGeometry | None


def _positive(value, maximum):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and isfinite(value) and 0 < value <= maximum)


def read_tree_model(path: Path) -> TreeDataset:
    """Read normalized inventory points; never invent missing measurements."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("type") != "FeatureCollection":
        raise ValueError("Tree file must be a GeoJSON FeatureCollection")
    metadata = raw.get("metadata", {})
    if metadata.get("height_unit") != "m" or metadata.get("crown_radius_unit") != "m":
        raise ValueError("Normalized tree height and crown radius units must explicitly be meters")
    if metadata.get("coordinate_reference_system") != "EPSG:4326":
        raise ValueError("Normalized trees must explicitly use EPSG:4326")
    trees = []
    unmodeled = 0
    seen = set()
    for feature in raw["features"]:
        point = shape(feature["geometry"])
        if point.geom_type != "Point" or point.is_empty or point.has_z or not point.is_valid:
            raise ValueError("Each tree geometry must be a valid 2D WGS84 Point")
        if not (-118.49 <= point.x <= -118.40 and 34.04 <= point.y <= 34.10):
            raise ValueError("Tree coordinates must lie inside UCLA service bounds")
        props = feature.get("properties", {})
        identity = str(props.get("globalid") or props.get("tree_id") or "")
        if not identity or identity in seen:
            raise ValueError("Each tree requires a unique globalid or tree_id")
        seen.add(identity)
        height, radius = props.get("height_m"), props.get("crown_radius_m")
        if props.get("status") != "tree" or not _positive(height, 100) or not _positive(radius, 50):
            unmodeled += 1
            continue
        crown_base = props.get("crown_base_m")
        if crown_base is not None and (isinstance(crown_base, bool) or not isinstance(crown_base, (int, float))
                                       or not isfinite(crown_base) or not 0 <= crown_base < height):
            raise ValueError("Crown base must be finite, nonnegative and below tree height")
        trees.append(TreeCrown(Point(*PROJECTION.transform(point.x, point.y)), float(height), float(radius),
                               str(props.get("tree_id") or identity), crown_base))
    coverage = metadata.get("coverage_geometry")
    coverage = _project_polygon(coverage) if coverage is not None else None
    return TreeDataset(
        tuple(trees), metadata.get("source"), metadata.get("data_as_of"), unmodeled,
        metadata.get("coverage_complete_verified") is True and unmodeled == 0,
        coverage,
    )


# a 64-sided unit circle, half as many sides as buffer(quad_segs=32) gave,
# because unioning 25k crowns was most of a request. its corners sit half a step
# off the axes and a little outside the circle, so every edge touches the true
# outline at its middle (including on both axes, so widths stay exact) and the
# polygon covers the whole crown shadow while being under 0.1% too big
UNIT_CROWN = Polygon([(cos(a) / cos(pi / 64), sin(a) / cos(pi / 64))
                      for a in ((k + .5) * pi / 32 for k in range(64))])


def cast_tree_shadow(tree: TreeCrown, elevation_deg: float, azimuth_deg: float):
    """Ground projection of an opaque ellipsoid aligned with vertical.

    Inventory height is the crown TOP, not the elevation of a flat canopy disk.
    If crown base is absent, assume vertical semi-axis min(radius, height/2),
    explicitly a shape assumption rather than an invented measured dimension.
    Ellipsoid ground projection has semi-axes sqrt(r²+(rz*cot(alpha))²) and r,
    centered at z_center*cot(alpha) away from the sun. At zenith this is the
    horizontal crown footprint. A floating crown is NOT swept down to the stem.
    """
    if not _positive(tree.height_m, 100) or not _positive(tree.crown_radius_m, 50):
        raise ValueError("Tree height/radius must be finite positive meter values")
    if tree.center.geom_type != "Point" or tree.center.is_empty or not tree.center.is_valid or tree.center.has_z:
        raise ValueError("Tree center must be a valid 2D projected Point")
    if not all(isfinite(v) for v in (elevation_deg, azimuth_deg)) or not MIN_SOLAR_ELEVATION < elevation_deg <= 90:
        raise ValueError("Solar elevation must be greater than 2 and at most 90 degrees")
    base = tree.crown_base_m
    if base is not None and (isinstance(base, bool) or not isinstance(base, (int, float))
                             or not isfinite(base) or not 0 <= base < tree.height_m):
        raise ValueError("Crown base must be nonnegative and below tree height")
    radius = tree.crown_radius_m
    vertical_radius = min(radius, tree.height_m / 2) if base is None else (tree.height_m - base) / 2
    center_height = tree.height_m - vertical_radius
    cotangent = 1 / tan(radians(elevation_deg))
    major = sqrt(radius * radius + (vertical_radius * cotangent) ** 2)
    ellipse = scale(UNIT_CROWN, xfact=major, yfact=radius, origin=(0, 0))
    ellipse = rotate(ellipse, 270 - azimuth_deg, origin=(0, 0))
    reach = center_height * cotangent
    return translate(ellipse, xoff=tree.center.x - reach * sin(radians(azimuth_deg)),
                     yoff=tree.center.y - reach * cos(radians(azimuth_deg)))
