"""Turning positions in a photo into positions on the map."""
from math import atan, atan2, cos, degrees, exp, log, pi, radians, sin, sqrt, tan

R = 6378137.0  # web mercator sphere, which is what the aerial exports are drawn in
M_PER_DEG = 111_320.0


def to_mercator(lon: float, lat: float) -> tuple[float, float]:
    return R * radians(lon), R * log(tan(pi / 4 + radians(lat) / 2))


def from_mercator(x: float, y: float) -> tuple[float, float]:
    return degrees(x / R), degrees(2 * atan(exp(y / R)) - pi / 2)


# gemini gives image positions on a 0-1000 grid (x left to right, y top to
# bottom). an aerial export is a north-up web mercator image, so a grid
# position maps linearly in mercator meters, not in degrees of latitude.
def grid_to_lonlat(x: float, y: float, bbox: tuple[float, float, float, float],
                   crs: str = "EPSG:3857") -> tuple[float, float]:
    west, south, east, north = bbox
    if crs == "EPSG:4326":
        # a crop drawn in plain longitude/latitude is linear in degrees
        return west + (east - west) * x / 1000, north - (north - south) * y / 1000
    x0, y0 = to_mercator(west, south)
    x1, y1 = to_mercator(east, north)
    return from_mercator(x0 + (x1 - x0) * x / 1000, y1 - (y1 - y0) * y / 1000)


def local_xy(lon: float, lat: float, origin: tuple[float, float]) -> tuple[float, float]:
    return (lon - origin[0]) * M_PER_DEG * cos(radians(origin[1])), (lat - origin[1]) * M_PER_DEG


def meters_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    x, y = local_xy(b[0], b[1], a)
    return sqrt(x * x + y * y)


def offset(lon: float, lat: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """The point distance_m away from (lon, lat) along a compass bearing."""
    dx, dy = distance_m * sin(radians(bearing_deg)), distance_m * cos(radians(bearing_deg))
    return lon + dx / (M_PER_DEG * cos(radians(lat))), lat + dy / M_PER_DEG


def bbox_around(lon: float, lat: float, size_m: float) -> tuple[float, float, float, float]:
    half_lon = size_m / 2 / (M_PER_DEG * cos(radians(lat)))
    half_lat = size_m / 2 / M_PER_DEG
    return lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat


# mapillary gives a perspective camera's focal length as a fraction of the
# image width, so the horizontal field of view falls out of it. 70 degrees is
# a typical phone when the camera didn't say.
def horizontal_fov(focal: float | None) -> float:
    return 2 * degrees(atan(0.5 / focal)) if focal and focal > 0 else 70.0


def bearing_of(x: float, heading_deg: float, fov_deg: float, panorama: bool) -> float:
    """Compass bearing of a 0-1000 grid column, as seen from the camera."""
    if panorama:
        # an equirectangular panorama spans all 360 degrees, with the camera
        # heading in the middle of the image
        return (heading_deg + (x / 1000 - 0.5) * 360) % 360
    return (heading_deg + degrees(atan((x / 1000 - 0.5) * 2 * tan(radians(fov_deg / 2))))) % 360


def polygon_area_m2(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    origin = points[0]
    xy = [local_xy(lon, lat, origin) for lon, lat in points]
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(xy, xy[1:] + xy[:1]))) / 2


def centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def compass(a: tuple[float, float], b: tuple[float, float]) -> float:
    x, y = local_xy(b[0], b[1], a)
    return degrees(atan2(x, y)) % 360
