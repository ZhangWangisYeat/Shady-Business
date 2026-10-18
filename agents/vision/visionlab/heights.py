"""Building heights from their shadows in an aerial photo, with the sun found from buildings of known height.

an aerial photo only shows roofs from above, but every building throws a
shadow whose length is height / tan(sun elevation). naip doesn't record the
time of day, so the sun's position is found first: for each possible time on
the photo's date, the known buildings' shadows are predicted and compared with
the photo, and the time that fits best fixes the sun's direction and angle.
then any other building's height is its measured shadow length times tan(elevation).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import cos, radians, sin, tan

import numpy as np
from astral import Observer
from astral.sun import azimuth, elevation
from scipy import ndimage

from visionlab.imagery import Tile


@dataclass
class Sun:
    azimuth_deg: float
    elevation_deg: float
    time_utc: str
    fit_score: float
    calibration_buildings: int


def _direction(azimuth_deg: float) -> tuple[float, float]:
    """One pixel step along the shadow, as (row, col): shadows point away from the sun."""
    away = radians(azimuth_deg + 180)
    return -cos(away), sin(away)  # north is up (row decreases), east is right


def _shift(mask: np.ndarray, rows: float, cols: float) -> np.ndarray:
    return ndimage.shift(mask.astype(np.uint8), (rows, cols), order=0, mode="constant", cval=0).astype(bool)


def _crop(roof: np.ndarray, margin: int, *layers: np.ndarray):
    """A window around one roof, so each shift moves a few thousand pixels instead of the whole tile."""
    rows, cols = np.nonzero(roof)
    r0, r1 = max(0, rows.min() - margin), min(roof.shape[0], rows.max() + margin + 1)
    c0, c1 = max(0, cols.min() - margin), min(roof.shape[1], cols.max() + margin + 1)
    return [layer[r0:r1, c0:c1] for layer in (roof, *layers)]


def shadow_profile(roof: np.ndarray, dark: np.ndarray, blocked: np.ndarray, azimuth_deg: float, max_px: int) -> np.ndarray:
    """For each step away from the roof (in pixels), the share of newly swept ground that is dark.

    blocked pixels (other roofs, tree crowns, no data) are left out: a shadow
    falling on a tree or a roof can't be seen as dark ground, so it neither
    proves nor disproves anything.
    """
    roof, dark, blocked = _crop(roof, max_px + 2, dark, blocked)
    dr, dc = _direction(azimuth_deg)
    swept = roof.copy()
    shares = np.full(max_px, np.nan)
    for step in range(1, max_px + 1):
        moved = _shift(roof, dr * step, dc * step)
        ring = moved & ~swept & ~blocked
        swept |= moved
        if ring.sum() >= 3:
            shares[step - 1] = dark[ring].mean()
    return shares


def shadow_length_px(profile: np.ndarray, cut: float = 0.5, start_within: int = 8) -> float | None:
    """How far the shadow reaches from the roof edge, in pixels.

    the shadow may start a pixel or two out (the roof outline is soft, and
    a tall building leans in the photo), so it has to begin within the first
    few meters, then it ends where the swept ground turns mostly lit.
    """
    smooth = np.array([np.nanmean(profile[i:i + 3]) if np.any(~np.isnan(profile[i:i + 3])) else np.nan
                       for i in range(len(profile))])
    begins = next((i for i in range(min(start_within, len(smooth))) if not np.isnan(smooth[i]) and smooth[i] >= cut), None)
    if begins is None:
        return None  # no shadow beside the roof: under trees, or too low to see
    for step in range(begins, len(smooth)):
        if not np.isnan(smooth[step]) and smooth[step] < cut:
            return float(step + 1)
    return None  # the shadow runs off what we can see


def fit_sun(tiles: list[tuple[Tile, list[tuple[np.ndarray, float]], np.ndarray, np.ndarray]], date: str,
            lon: float, lat: float) -> Sun:
    """The time on `date` whose sun best explains the shadows of buildings with known heights.

    tiles: (tile, [(roof mask, height m)], dark ground mask, blocked mask).
    each candidate time predicts every known shadow's length; the score
    rewards dark ground inside the predicted shadow and lit ground just past it.
    """
    observer = Observer(latitude=lat, longitude=lon)
    day = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    best = None
    # 13:00-24:00 utc is 6 am to 5 pm in california summer time
    for minutes in range(13 * 60, 24 * 60, 10):
        when = day + timedelta(minutes=minutes)
        elev = elevation(observer, when)
        if elev < 15:
            continue
        az = azimuth(observer, when)
        scores = []
        for tile, known, dark, blocked in tiles:
            m = tile.meters_per_pixel
            for roof, height in known:
                predicted = height / tan(radians(elev)) / m
                if predicted < 2:
                    continue
                profile = shadow_profile(roof, dark, blocked, az, int(predicted * 1.5) + 2)
                inside = np.nanmean(profile[: int(predicted)]) if np.any(~np.isnan(profile[: int(predicted)])) else np.nan
                beyond = np.nanmean(profile[int(predicted) + 1:]) if np.any(~np.isnan(profile[int(predicted) + 1:])) else np.nan
                if not np.isnan(inside) and not np.isnan(beyond):
                    scores.append(inside - beyond)
        if scores and (best is None or np.mean(scores) > best[0]):
            best = (float(np.mean(scores)), az, elev, when, len(scores))
    if best is None:
        raise ValueError("No known building had a measurable shadow")
    score, az, elev, when, n = best
    return Sun(float(az), float(elev), when.isoformat(), round(score, 3), n)


def roof_heights(tile: Tile, roofs: np.ndarray, dark: np.ndarray, blocked: np.ndarray, sun: Sun,
                 max_height_m: float = 80) -> list[dict]:
    """Each roof region with its height from its shadow (None where the shadow can't be measured)."""
    labels, count = ndimage.label(roofs)
    m = tile.meters_per_pixel
    max_px = int(max_height_m / tan(radians(sun.elevation_deg)) / m) + 3
    found = []
    for region in range(1, count + 1):
        roof = labels == region
        if roof.sum() * m * m < 20:
            continue
        others = roofs & ~roof
        length = shadow_length_px(shadow_profile(roof, dark, blocked | others, sun.azimuth_deg, max_px))
        height = None if length is None else round(min(max_height_m, max(3.0, length * m * tan(radians(sun.elevation_deg)))), 1)
        found.append({"mask": roof, "height_m": height, "shadow_m": None if length is None else round(length * m, 1)})
    return found
