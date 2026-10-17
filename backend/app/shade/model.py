"""Optional geometry-derived shade. No building file => all segments unknown."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from functools import lru_cache
from math import tan, radians, sin, cos
from shapely.geometry import shape, Point
from shapely.affinity import translate
from shapely.ops import unary_union, transform
from pyproj import Transformer
from app.settings import SHADE_FILE

PROJECTION = Transformer.from_crs("EPSG:4326", "EPSG:26911",always_xy=True)

@dataclass(frozen=True)
class ShadeModel:
    shapes: tuple  # (building footprint projected, height meters)
    data_as_of: str | None
    coverage_complete_verified: bool

@lru_cache(maxsize=1)
def load_model() -> ShadeModel | None:
    if not SHADE_FILE.is_file(): return None
    raw=json.loads(Path(SHADE_FILE).read_text())
    if raw.get('type') != 'FeatureCollection': raise ValueError('building file must be GeoJSON FeatureCollection')
    shapes=[]
    for feature in raw['features']:
        h=feature.get('properties',{}).get('height_m')
        if not isinstance(h,(int,float)) or not 1 <= h <= 250: continue
        poly=transform(PROJECTION.transform,shape(feature['geometry']))
        if poly.is_valid and not poly.is_empty: shapes.append((poly,float(h)))
    if not shapes: return None
    return ShadeModel(tuple(shapes), raw.get('metadata',{}).get('data_as_of'), raw.get('metadata',{}).get('coverage_complete_verified') is True)


def shadow_polygons(model: ShadeModel, when: datetime):
    """Planar opaque obstructions on level terrain; rough model, not solar-grade analysis."""
    from astral import LocationInfo
    from astral.sun import azimuth, elevation
    site=LocationInfo(latitude=34.0689,longitude=-118.4452,timezone='America/Los_Angeles')
    el=elevation(site.observer,when)
    if el <= 2: return None  # twilight/unreliable: don't pretend daylight model works
    heading=azimuth(site.observer,when)
    polygons=[]
    for base,height in model.shapes:
        d=min(250,height/tan(radians(el)))
        # Sun azimuth measured clockwise from north; shadow goes away from it.
        dx=-d*sin(radians(heading)); dy=-d*cos(radians(heading))
        far=translate(base,xoff=dx,yoff=dy)
        polygons.append(base.union(far).convex_hull)
    return unary_union(polygons)


def fraction_sun(shadows, coords: list[tuple[float,float]], n: int = 9) -> float | None:
    if shadows is None: return None
    from shapely.geometry import LineString
    line=transform(PROJECTION.transform,LineString(coords))
    if line.length < .01: return 0.0
    hits=0
    for i in range(n):
        p=line.interpolate(line.length * (i+0.5)/n)
        hits += bool(shadows.covers(p))
    return 1.0-hits/n
