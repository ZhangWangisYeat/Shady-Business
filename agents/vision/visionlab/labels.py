"""Turning labeled examples (GeoJSON polygons, or points with a radius) into a training mask for a tile."""
import numpy as np
from shapely.affinity import scale, translate
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from skimage.draw import polygon as fill_polygon

from visionlab.imagery import M_PER_DEG, Tile


def geometries(features: list[dict], radius_property: str | None = None, default_radius_m: float | None = None) -> list[BaseGeometry]:
    """Example shapes in longitude/latitude.

    a point becomes a disc when it has a radius: that's how a tree inventory
    (a point per trunk plus a crown spread) becomes crown-shaped labels.
    """
    found = []
    for feature in features:
        geom = shape(feature["geometry"])
        if geom.geom_type == "Point":
            radius = (feature.get("properties") or {}).get(radius_property) if radius_property else None
            radius = radius or default_radius_m
            if not radius:
                continue
            # a degree of longitude is shorter than a degree of latitude here,
            # so the disc is an ellipse in degrees and round on the ground
            disc = Point(0, 0).buffer(1, 16)
            disc = scale(disc, radius / (M_PER_DEG * np.cos(np.radians(geom.y))), radius / M_PER_DEG, origin=(0, 0))
            found.append(translate(disc, geom.x, geom.y))
        elif geom.geom_type in ("Polygon", "MultiPolygon"):
            found.append(geom)
    return found


def rasterize(tile: Tile, shapes: list[BaseGeometry]) -> np.ndarray:
    """A bool mask: true where any shape covers the pixel center."""
    mask = np.zeros(tile.shape, bool)
    height, width = tile.shape
    for geom in shapes:
        for part in getattr(geom, "geoms", [geom]):
            rows, cols = zip(*(tile.lonlat_to_pixel(lon, lat) for lon, lat in part.exterior.coords))
            rr, cc = fill_polygon(np.array(rows) - 0.5, np.array(cols) - 0.5, (height, width))
            mask[rr, cc] = True
            for hole in part.interiors:
                rows, cols = zip(*(tile.lonlat_to_pixel(lon, lat) for lon, lat in hole.coords))
                rr, cc = fill_polygon(np.array(rows) - 0.5, np.array(cols) - 0.5, (height, width))
                mask[rr, cc] = False
    return mask
