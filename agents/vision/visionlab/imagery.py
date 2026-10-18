"""Aerial imagery for any small area: USDA NAIP (0.6 m, red/green/blue/near-infrared, public domain)."""
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from math import cos, radians
from pathlib import Path

import numpy as np
from PIL import Image

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
CROP = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
USER_AGENT = "visionlab/0.1 (Shady Business, LA Hacks 2026)"
CACHE = Path(__file__).resolve().parents[1] / "data" / "tiles"
M_PER_DEG = 111_320.0
NAIP_M = 0.6  # california naip ground resolution


class ImageryUnavailable(Exception):
    """No imagery for the area, or the imagery service failed after retries."""


@dataclass
class Tile:
    """A north-up image in plain longitude/latitude, so pixels map to the map linearly."""
    pixels: np.ndarray  # height x width x 4 (red, green, blue, near infrared), 0-255
    valid: np.ndarray  # height x width bool: false where the source had no data
    bbox: tuple[float, float, float, float]  # west, south, east, north
    source: str
    captured: str

    @property
    def shape(self) -> tuple[int, int]:
        return self.pixels.shape[:2]

    def pixel_to_lonlat(self, row: float, col: float) -> tuple[float, float]:
        west, south, east, north = self.bbox
        height, width = self.shape
        return west + (east - west) * col / width, north - (north - south) * row / height

    def lonlat_to_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        west, south, east, north = self.bbox
        height, width = self.shape
        return (north - lat) / (north - south) * height, (lon - west) / (east - west) * width

    @property
    def meters_per_pixel(self) -> float:
        west, south, east, north = self.bbox
        return (east - west) * M_PER_DEG * cos(radians((south + north) / 2)) / self.shape[1]


def bbox_around(lon: float, lat: float, size_m: float) -> tuple[float, float, float, float]:
    half_lon = size_m / 2 / (M_PER_DEG * cos(radians(lat)))
    half_lat = size_m / 2 / M_PER_DEG
    return lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat


def _request(url: str, body: bytes | None = None, timeout: float = 60) -> bytes:
    headers = {"User-Agent": USER_AGENT, **({"Content-Type": "application/json"} if body else {})}
    # one retry with a pause: the service is free and usually fast, but a
    # single dropped connection shouldn't fail a whole analysis
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt:
                raise ImageryUnavailable(f"Imagery service failed: {exc}") from exc
            time.sleep(3)
    raise AssertionError("unreachable")


def _png(data: bytes) -> np.ndarray:
    if data[1:4] != b"PNG":
        raise ImageryUnavailable(f"Imagery service returned an error: {data[:120]!r}")
    return np.asarray(Image.open(io.BytesIO(data)))


def fetch_tile(bbox: tuple[float, float, float, float], resolution_m: float = NAIP_M, cache: Path = CACHE) -> Tile:
    """The newest NAIP image covering bbox, cropped to it, with all four bands."""
    key = hashlib.sha1(json.dumps([round(v, 6) for v in bbox] + [resolution_m]).encode()).hexdigest()[:16]
    cached = cache / f"{key}.npz"
    if cached.exists():
        saved = np.load(cached, allow_pickle=False)
        return Tile(saved["pixels"], saved["valid"], tuple(saved["bbox"]), str(saved["source"]), str(saved["captured"]))

    search = json.dumps({"collections": ["naip"], "bbox": list(bbox), "limit": 5,
                         "sortby": [{"field": "datetime", "direction": "desc"}]}).encode()
    items = json.loads(_request(STAC, search))["features"]
    if not items:
        raise ImageryUnavailable("No NAIP imagery covers this area")
    # the newest survey year, and within it the image covering most of the
    # area (an area on a quad edge touches two images)
    newest = items[0]["properties"]["datetime"][:4]
    item = items[0] if len(items) == 1 else max(
        (i for i in items if i["properties"]["datetime"][:4] == newest), key=lambda i: _overlap(i["bbox"], bbox))
    west, south, east, north = bbox
    width = max(32, round((east - west) * M_PER_DEG * cos(radians((south + north) / 2)) / resolution_m))
    height = max(32, round((north - south) * M_PER_DEG / resolution_m))
    corners = ",".join(f"{v:.7f}" for v in bbox)
    base = f"{CROP}/{corners}/{width}x{height}.png?collection=naip&item={item['id']}&assets=image"
    # two requests because a png holds at most four channels and one of them
    # is the no-data mask: colour first, then near infrared on its own
    rgb = _png(_request(base + "&asset_bidx=image%7C1,2,3"))
    nir = _png(_request(base + "&asset_bidx=image%7C4"))
    pixels = np.dstack([rgb[..., :3], nir[..., 0]]).astype(np.uint8)
    valid = (rgb[..., 3] > 0) if rgb.shape[2] == 4 else np.ones(pixels.shape[:2], bool)
    tile = Tile(pixels, valid, bbox, f"USDA NAIP {item['id']} via Microsoft Planetary Computer",
                item["properties"]["datetime"][:10])
    cache.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cached, pixels=tile.pixels, valid=tile.valid, bbox=np.array(bbox), source=tile.source, captured=tile.captured)
    return tile


def _overlap(a, b) -> float:
    w, s, e, n = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return max(0, e - w) * max(0, n - s)


def tile_from_image(path: Path, bbox: tuple[float, float, float, float] | None = None) -> Tile:
    """Any user image (no near infrared). Without a bbox, positions stay in pixels."""
    rgb = np.asarray(Image.open(path).convert("RGB"))
    height, width = rgb.shape[:2]
    pixels = np.dstack([rgb, np.zeros((height, width), np.uint8)])
    return Tile(pixels, np.ones((height, width), bool), bbox or (0, -height, width, 0), f"image {Path(path).name}", "unknown")
