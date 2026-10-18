"""From a pixel mask to polygons on the map, and from a canopy to individual crowns."""
from math import pi, sqrt

import numpy as np
from scipy import ndimage
from shapely.geometry import Polygon, mapping
from skimage.feature import peak_local_max
from skimage.measure import find_contours, label, regionprops
from skimage.morphology import closing, disk, opening, remove_small_objects
from skimage.segmentation import watershed

from visionlab.imagery import Tile


def clean(mask: np.ndarray, tile: Tile, min_area_m2: float = 4.0, smooth_m: float = 1.2) -> np.ndarray:
    """Remove speckle and fill pinholes, sized in meters so it behaves the same at any resolution."""
    radius = max(1, round(smooth_m / tile.meters_per_pixel))
    mask = closing(opening(mask, disk(radius)), disk(radius)).astype(bool)
    return remove_small_objects(mask, max_size=max(1, round(min_area_m2 / tile.meters_per_pixel ** 2)))


def polygons(mask: np.ndarray, tile: Tile, simplify_m: float = 0.6) -> list[Polygon]:
    """Outline each connected patch. holes (a courtyard in a canopy) are kept."""
    simplify = simplify_m / 111_320
    found = []
    for region in regionprops(label(mask)):
        r0, c0, r1, c1 = region.bbox
        patch = np.pad(region.image, 1)
        rings = []
        for contour in find_contours(patch.astype(float), 0.5):
            ring = [tile.pixel_to_lonlat(r0 + r - 1 + 0.5, c0 + c - 1 + 0.5) for r, c in contour]
            if len(ring) >= 4:
                rings.append(Polygon(ring))
        if not rings:
            continue
        rings.sort(key=lambda p: -p.area)
        outer = rings[0]
        holes = [r.exterior.coords for r in rings[1:] if outer.contains(r)]
        poly = Polygon(outer.exterior.coords, holes).buffer(0).simplify(simplify, preserve_topology=True)
        if not poly.is_empty:
            found.extend(getattr(poly, "geoms", [poly]))
    return found


def crowns(mask: np.ndarray, tile: Tile, min_crown_radius_m: float = 1.5, min_spacing_m: float = 2.5) -> list[dict]:
    """Split a canopy mask into individual crowns.

    each crown is a hill in the distance-to-edge map (the middle of a crown is
    the point furthest from open ground), so a watershed from those peaks
    separates trees whose crowns touch. a crown's size is reported as the
    radius of a circle with the same area, the same thing an inventory's
    "spread / 2" means.
    """
    m = tile.meters_per_pixel
    distance = ndimage.distance_transform_edt(mask)
    peaks = peak_local_max(distance, min_distance=max(1, round(min_spacing_m / m)),
                           threshold_abs=min_crown_radius_m / m * 0.6, labels=label(mask))
    markers = np.zeros(mask.shape, int)
    for i, (r, c) in enumerate(peaks, 1):
        markers[r, c] = i
    segments = watershed(-distance, markers, mask=mask)
    found = []
    for region in regionprops(segments):
        area_m2 = region.area * m * m
        radius = sqrt(area_m2 / pi)
        if radius < min_crown_radius_m:
            continue
        r, c = region.centroid
        lon, lat = tile.pixel_to_lonlat(r + 0.5, c + 0.5)
        found.append({"lon": lon, "lat": lat, "crown_radius_m": radius, "area_m2": area_m2,
                      # how far the crown reaches from its middle, a check that
                      # the equal-area circle isn't hiding a long thin shape
                      "max_reach_m": float(distance[segments == region.label].max() * m)})
    return found


def feature_collection(polys: list[Polygon], properties: dict) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(p), "properties": {**properties, "area_m2": round(_area_m2(p), 1)}} for p in polys]}


def _area_m2(poly: Polygon) -> float:
    lat = poly.centroid.y
    return poly.area * 111_320 ** 2 * np.cos(np.radians(lat))
