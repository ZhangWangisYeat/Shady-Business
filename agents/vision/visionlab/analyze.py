"""The jobs VisionLab does: analyze an area, train a new target from examples, compare against a dataset."""
import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from visionlab.allometry import HeightModel
from visionlab.compare import _center, match_points
from visionlab.imagery import Tile, bbox_around, fetch_tile
from visionlab.labels import geometries, rasterize
from visionlab.models import EXPERTS, MODELS, PixelModel, shadow, vegetation, water
from visionlab.vectorize import clean, crowns, feature_collection, polygons

# what each target is called in a request, mapped to how it's detected
ALIASES = {
    "tree_canopy": ["tree", "trees", "canopy", "tree canopy", "crowns"],
    "vegetation": ["vegetation", "plants", "greenery", "green space", "grass"],
    "water": ["water", "pools", "pool", "ponds", "fountains"],
    "shadow": ["shadow", "shadows", "shaded ground"],
    "building": ["building", "buildings", "roof", "roofs", "rooftops"],
    "land_cover": ["land cover", "landcover", "classify", "everything", "map the area", "what's there", "what is there"],
}


def resolve_target(text: str) -> str | None:
    text = text.lower().strip()
    # a full land-cover map first: "classify everything" mentions trees too
    if any(w in text for w in ALIASES["land_cover"]):
        return "land_cover"
    for name in PixelModel.available():
        if name.replace("_", " ") in text or name in text:
            return name
    for target, words in ALIASES.items():
        if any(w in text for w in words):
            return target
    return None


def _height_model(name: str = "tree_height.json") -> HeightModel | None:
    path = MODELS / name
    if not path.exists():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    return HeightModel(saved["slope"], saved["intercept"], saved["mae_m"], saved["within_25pct"], saved["trees"])


def detect_mask(tile: Tile, target: str) -> tuple[np.ndarray, str]:
    """The mask for a target, and which model produced it (trained beats built-in)."""
    if target in PixelModel.available():
        return PixelModel.load(target).predict(tile), f"trained:{target}"
    if target == "tree_canopy":
        # no trained canopy model yet: vegetation is the honest fallback, and
        # the answer says so, since it can't tell a lawn from a tree
        return vegetation(tile), "builtin:vegetation (untrained fallback)"
    if target in EXPERTS:
        return EXPERTS[target](tile), f"builtin:{target}"
    if target == "building":
        raise ValueError("No building model trained yet: run train.py --target building")
    raise ValueError(f"Unknown target {target!r}. Known: {', '.join(sorted(set(ALIASES) | set(PixelModel.available())))}")


def _roofs(tile: Tile) -> np.ndarray:
    if "building" not in PixelModel.available():
        return np.zeros(tile.shape, bool)
    return clean(PixelModel.load("building").predict(tile), tile, min_area_m2=20)


# when two classes claim the same pixel, the first one here wins: water and
# roofs are the most certain, a tree crown over a lawn is still a tree, and
# shade/sun only applies to whatever ground is left
COVER_ORDER = ["water", "building", "tree_canopy", "other_vegetation", "ground_shade", "ground_sun"]


def land_cover(lon: float, lat: float, size_m: float) -> dict:
    """Every pixel classified, as polygons and area shares: one call for 'what's here'."""
    size_m = float(min(max(size_m, 40), 600))
    tile = fetch_tile(bbox_around(lon, lat, size_m))
    canopy, canopy_model = detect_mask(tile, "tree_canopy")
    layers = {"water": clean(water(tile), tile, min_area_m2=6), "building": _roofs(tile),
              "tree_canopy": clean(canopy, tile)}
    layers["other_vegetation"] = clean(vegetation(tile), tile)
    shade = shadow(tile, exclude=layers["tree_canopy"] | layers["other_vegetation"] | layers["building"])
    layers["ground_shade"] = clean(shade, tile, min_area_m2=2)
    claimed = np.zeros(tile.shape, bool)
    shares, polys = {}, {}
    for name in COVER_ORDER:
        if name == "ground_sun":
            layer = tile.valid & ~claimed
        else:
            layer = layers[name] & tile.valid & ~claimed
        claimed |= layer
        shares[name] = round(float(layer.sum() / max(tile.valid.sum(), 1)), 3)
        polys[name] = feature_collection(polygons(clean(layer, tile, min_area_m2=4), tile), {"class": name})
    # wildfire defensible space: how much of the ground within 30 m of the
    # roofs is vegetation (california asks for lean, clean vegetation there)
    defensible = None
    if layers["building"].any():
        zone = ndimage.distance_transform_edt(~layers["building"]) <= round(30 / tile.meters_per_pixel)
        zone &= ~layers["building"] & tile.valid
        green = layers["tree_canopy"] | layers["other_vegetation"]
        defensible = {"zone_m": 30, "vegetation_share_in_zone": round(float((green & zone).sum() / max(zone.sum(), 1)), 3),
                      "tree_canopy_share_in_zone": round(float((layers["tree_canopy"] & zone).sum() / max(zone.sum(), 1)), 3)}
    heights = _height_model()
    found = crowns(layers["tree_canopy"], tile)
    for crown in found:
        crown["height_m"] = round(heights.predict(crown["crown_radius_m"]), 1) if heights else None
    return {"target": "land_cover", "center": [lon, lat], "size_m": size_m,
            "models": {"tree_canopy": canopy_model, "building": "trained:building" if "building" in PixelModel.available() else "none",
                       "water": "builtin:water", "vegetation": "builtin:vegetation", "shade": "builtin:shadow"},
            "imagery": {"source": tile.source, "captured": tile.captured, "meters_per_pixel": round(tile.meters_per_pixel, 2),
                        "license": "Public domain (USDA NAIP)"},
            "shares": shares, "crowns": [{k: (round(v, 7) if k in ("lon", "lat") else round(v, 2) if isinstance(v, float) else v)
                                          for k, v in c.items()} for c in found],
            "defensible_space": defensible,
            "ground_shade_share": round(shares["ground_shade"] / max(shares["ground_shade"] + shares["ground_sun"], 1e-9), 3),
            "shade_at": f"photo time ({tile.captured}); shadows move through the day",
            "layers": polys}


def analyze_area(lon: float, lat: float, size_m: float, target: str, reference: list[dict] | None = None,
                 reference_radius: str | None = "crown_radius_m") -> dict:
    """Everything about one target in one square area, as JSON.

    for trees it also splits the canopy into crowns with a height estimate,
    and classifies the open ground around them into shade and sun as seen in
    the photo. with a reference dataset, each crown is checked against it.
    """
    size_m = float(min(max(size_m, 40), 600))  # big enough to be useful, small enough to answer in seconds
    tile = fetch_tile(bbox_around(lon, lat, size_m))
    raw, model_used = detect_mask(tile, target)
    mask = clean(raw, tile)
    area_px = tile.valid.sum()
    m2 = tile.meters_per_pixel ** 2
    result = {
        "target": target, "model": model_used, "center": [lon, lat], "size_m": size_m,
        "imagery": {"source": tile.source, "captured": tile.captured, "meters_per_pixel": round(tile.meters_per_pixel, 2),
                    "license": "Public domain (USDA NAIP)"},
        "coverage_share": round(float(mask.sum() / area_px), 3) if area_px else 0.0,
        "area_m2": round(float(mask.sum() * m2), 1),
        "polygons": feature_collection(polygons(mask, tile), {"class": target}),
    }
    if target == "building":
        model = _height_model("building_height.json")
        for feature in result["polygons"]["features"]:
            radius = (feature["properties"]["area_m2"] / np.pi) ** 0.5
            feature["properties"]["height_m"] = round(min(60.0, max(3.0, model.predict(radius))), 1) if model else None
        result["height_model"] = ({"method": "log-log fit of building height vs roof size, from measured buildings",
                                   "mean_abs_error_m": model.mae_m} if model else None)
    if target == "tree_canopy":
        heights = _height_model()
        found = crowns(mask, tile)
        for crown in found:
            crown["height_m"] = round(heights.predict(crown["crown_radius_m"]), 1) if heights else None
        # open ground = everything that isn't canopy or roof; shade there is
        # whatever is dark at photo time (tree and building shadows), the rest
        # is sun. roofs come from the trained building model (without it they'd
        # count as sunny ground, since a flat roof looks like a plaza)
        roofs = _roofs(tile)
        shade = clean(shadow(tile, exclude=raw | roofs), tile, min_area_m2=2)
        open_ground = tile.valid & ~mask & ~roofs
        sun = open_ground & ~shade
        result["crowns"] = [{k: (round(v, 7) if k in ("lon", "lat") else round(v, 2) if isinstance(v, float) else v)
                             for k, v in c.items()} for c in found]
        result["height_model"] = ({"method": "log-log fit of inventory height vs crown radius",
                                   "mean_abs_error_m": heights.mae_m, "trained_on_trees": heights.trained_on} if heights else None)
        result["ground"] = {
            "shade_share_of_open_ground": round(float(shade.sum() / max(open_ground.sum(), 1)), 3),
            "shade_m2": round(float(shade.sum() * m2), 1), "sun_m2": round(float(sun.sum() * m2), 1),
            "at": f"photo time ({tile.captured}); shadows move through the day",
            "shade_polygons": feature_collection(polygons(shade, tile), {"class": "shade", "at_photo_time": True}),
            "sun_polygons": feature_collection(polygons(clean(sun, tile, min_area_m2=6), tile), {"class": "sun", "at_photo_time": True}),
        }
    if reference is not None:
        west, south, east, north = tile.bbox
        # a reference object is placed by its middle, whether it's a point
        # (a tree) or a polygon (a building footprint)
        centers = [(f, _center(f["geometry"])) for f in reference]
        inside = [f for f, (lon, lat) in centers if west <= lon <= east and south <= lat <= north]
        detections = result.get("crowns") or [{"lon": p.centroid.x, "lat": p.centroid.y} for p in polygons(mask, tile)]
        polygonal = bool(inside) and inside[0]["geometry"]["type"] != "Point"
        # a building's middle and its detected roof's middle can be 10+ m
        # apart on a big building, so polygons get a wider reach than trunks
        compared = match_points(detections, inside, max_m=15.0 if polygonal else 4.0,
                                reference_radius=None if polygonal else reference_radius)
        under = 0
        for f in inside:
            r, c = tile.lonlat_to_pixel(*_center(f["geometry"]))
            under += bool(0 <= r < mask.shape[0] and 0 <= c < mask.shape[1] and mask[int(r), int(c)])
        result["comparison"] = {
            "reference_objects_in_area": len(inside), "matched": len(compared["matches"]),
            "new_not_in_reference": len(compared["new"]), "reference_not_detected": len(compared["missed"]),
            "reference_under_detected_area": under,
            # no reference objects here usually means the dataset never
            # covered this ground, not that there's nothing here
            "reference_covers_area": bool(inside),
            "new_indices": compared["new"],
        }
    return result


def train_from_examples(target: str, examples: list[dict], radius_property: str | None = None,
                        default_radius_m: float | None = None, tile_size_m: float = 160, max_tiles: int = 12) -> dict:
    """Teach VisionLab a new target from labeled GeoJSON (polygons, or points with a radius).

    the examples are grouped into tiles over their own extent; within each
    tile, everything not labeled counts as "not this", so the examples should
    be complete for the area they cover.
    """
    shapes = geometries(examples, radius_property, default_radius_m)
    if len(shapes) < 5:
        raise ValueError("Need at least 5 labeled examples to learn from")
    centers = np.array([[g.centroid.x, g.centroid.y] for g in shapes])
    step = tile_size_m / 111_320
    cells = {}
    for (lon, lat), geom in zip(centers, shapes):
        key = (int(lon / (step / np.cos(np.radians(lat)))), int(lat / step))
        cells.setdefault(key, []).append(geom)
    busiest = sorted(cells.values(), key=len, reverse=True)[:max_tiles]
    tiles, masks = [], []
    for group in busiest:
        lon, lat = np.mean([[g.centroid.x, g.centroid.y] for g in group], axis=0)
        tile = fetch_tile(bbox_around(lon, lat, tile_size_m))
        tiles.append(tile)
        masks.append(rasterize(tile, shapes))
    model = PixelModel(target).fit(tiles, masks)
    path = model.save()
    return {"target": target, "saved": str(path.name), **model.trained_on, "examples": len(shapes)}
