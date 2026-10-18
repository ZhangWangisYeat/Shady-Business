"""Street-level photos (Mapillary): how green the view is and how much of the ground is shaded.

an aerial photo sees canopy from above; a street photo sees it the way a
person walking does. the green view index (the share of a street photo that is
vegetation) is the standard measure for this in urban forestry, so it's what
VisionLab reports, and it's a ground-level check on the aerial canopy maps.
"""
import io
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import numpy as np
from PIL import Image

from visionlab.imagery import bbox_around

GRAPH = "https://graph.mapillary.com/images"
FIELDS = "id,captured_at,compass_angle,computed_geometry,geometry,is_pano,thumb_1024_url,creator"


def analyze_photo(pixels: np.ndarray) -> dict:
    """Green view index, sky share and shaded ground share for one photo (RGB, 0-255)."""
    rgb = pixels[..., :3].astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    brightness = rgb.mean(axis=2)
    # vegetation: green clearly above red and blue. excess green is the usual
    # index for plain colour photos (no near infrared at street level)
    green = (2 * g - r - b > 20) & (g > 40)
    # sky: bright and blue-ish, in the top part of the frame
    height = pixels.shape[0]
    rows = np.arange(height)[:, None] < height * 0.6
    sky = rows & (b > r + 5) & (brightness > 140) & ~green
    # ground: the bottom third, minus plants; shaded where it's dark
    ground = (np.arange(height)[:, None] > height * 2 / 3) & ~green & np.ones_like(green)
    if ground.sum():
        cut = min(np.median(brightness[ground]) * 0.65, 90)
        shaded = ground & (brightness < cut)
        shade_share = float(shaded.sum() / ground.sum())
    else:
        shade_share = None
    return {"green_view_index": round(float(green.mean()), 3), "sky_share": round(float(sky.mean()), 3),
            "ground_shade_share": None if shade_share is None else round(shade_share, 3)}


def photos_near(lon: float, lat: float, radius_m: float, token: str, limit: int = 6) -> list[dict]:
    """The newest Mapillary photos near a point, facing different ways."""
    bbox = bbox_around(lon, lat, radius_m * 2)
    query = urllib.parse.urlencode({"fields": FIELDS, "bbox": ",".join(f"{v:.6f}" for v in bbox), "limit": 100})
    request = urllib.request.Request(f"{GRAPH}?{query}", headers={"Authorization": f"OAuth {token}", "User-Agent": "visionlab/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        found = [i for i in json.load(response)["data"] if i.get("thumb_1024_url")]
    found.sort(key=lambda i: -(i.get("captured_at") or 0))
    picked = []
    for image in found:
        heading = image.get("compass_angle") or 0
        if all(abs((heading - p["compass_angle"] + 180) % 360 - 180) >= 45 for p in picked):
            picked.append({**image, "compass_angle": heading})
        if len(picked) == limit:
            break
    return picked


def analyze_near(lon: float, lat: float, radius_m: float, token: str, limit: int = 6) -> dict:
    results = []
    for image in photos_near(lon, lat, radius_m, token, limit):
        with urllib.request.urlopen(urllib.request.Request(image["thumb_1024_url"], headers={"User-Agent": "visionlab/0.1"}), timeout=30) as r:
            pixels = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB"))
        where = (image.get("computed_geometry") or image.get("geometry") or {}).get("coordinates")
        results.append({"id": image["id"], "coordinate": where, "heading": round(image["compass_angle"]),
                        "captured": datetime.fromtimestamp(image["captured_at"] / 1000, timezone.utc).date().isoformat() if image.get("captured_at") else None,
                        "url": f"https://www.mapillary.com/app/?pKey={image['id']}",
                        "credit": f"© {(image.get('creator') or {}).get('username', 'Mapillary contributor')}, CC BY-SA 4.0",
                        **analyze_photo(pixels)})
    gvi = [p["green_view_index"] for p in results]
    shade = [p["ground_shade_share"] for p in results if p["ground_shade_share"] is not None]
    return {"center": [lon, lat], "radius_m": radius_m, "photos": results,
            "mean_green_view_index": round(float(np.mean(gvi)), 3) if gvi else None,
            "mean_ground_shade_share": round(float(np.mean(shade)), 3) if shade else None,
            "source": "Mapillary street-level imagery (CC BY-SA 4.0)"}
