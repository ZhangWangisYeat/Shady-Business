"""Drawing a result over its aerial photo, so a person can check it at a glance."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from visionlab.imagery import Tile


def overlay(tile: Tile, result: dict, out: Path, reference: list[dict] | None = None, scale: int = 2) -> Path:
    """Canopy outlines in green, crowns as dots, photo-time shade in blue, reference trees as yellow rings."""
    base = Image.fromarray(tile.pixels[..., :3]).resize((tile.shape[1] * scale, tile.shape[0] * scale), Image.LANCZOS)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    to_px = lambda lon, lat: tuple(v * scale for v in reversed(tile.lonlat_to_pixel(lon, lat)))
    for feature in (result.get("ground") or {}).get("shade_polygons", {}).get("features", []):
        for ring in _rings(feature["geometry"]):
            draw.polygon([to_px(*p) for p in ring], fill=(40, 90, 255, 70))
    for feature in result["polygons"]["features"]:
        for ring in _rings(feature["geometry"]):
            draw.line([to_px(*p) for p in ring] + [to_px(*ring[0])], fill=(40, 255, 90, 255), width=2)
    for crown in result.get("crowns", []):
        x, y = to_px(crown["lon"], crown["lat"])
        r = crown["crown_radius_m"] / tile.meters_per_pixel * scale
        draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255, 160), width=1)
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(255, 255, 255, 255))
    for feature in reference or []:
        lon, lat = feature["geometry"]["coordinates"][:2]
        x, y = to_px(lon, lat)
        if 0 <= x < base.size[0] and 0 <= y < base.size[1]:
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 220, 0, 255), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB").save(out)
    return out


COLORS = {"water": (40, 160, 255, 140), "building": (255, 140, 0, 110), "tree_canopy": (30, 200, 70, 120),
          "other_vegetation": (170, 230, 80, 90), "ground_shade": (60, 60, 200, 110), "ground_sun": (255, 230, 120, 50)}


def cover_overlay(tile: Tile, result: dict, out: Path, scale: int = 2) -> Path:
    """Each land-cover class tinted its own colour over the photo."""
    base = Image.fromarray(tile.pixels[..., :3]).resize((tile.shape[1] * scale, tile.shape[0] * scale), Image.LANCZOS)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    to_px = lambda lon, lat: tuple(v * scale for v in reversed(tile.lonlat_to_pixel(lon, lat)))
    for name, colour in COLORS.items():
        for feature in result["layers"][name]["features"]:
            for ring in _rings(feature["geometry"]):
                draw.polygon([to_px(*p) for p in ring], fill=colour)
    for crown in result["crowns"]:
        x, y = to_px(crown["lon"], crown["lat"])
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(255, 255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB").save(out)
    return out


def _rings(geometry: dict):
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for poly in polys:
        yield poly[0]
