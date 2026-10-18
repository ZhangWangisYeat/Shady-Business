"""Checking detections against a reference dataset: what matched, what we missed, what's new."""
from math import cos, radians, sqrt

import numpy as np
from shapely.geometry import shape

M_PER_DEG = 111_320.0


def meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = (b[0] - a[0]) * M_PER_DEG * cos(radians(a[1]))
    dy = (b[1] - a[1]) * M_PER_DEG
    return sqrt(dx * dx + dy * dy)


def mask_scores(predicted: np.ndarray, truth: np.ndarray, valid: np.ndarray) -> dict:
    """Pixel agreement. iou is the strict one: overlap over everything either side marked."""
    p, t = predicted & valid, truth & valid
    inter, union = (p & t).sum(), (p | t).sum()
    return {"iou": float(inter / union) if union else None,
            "precision": float(inter / p.sum()) if p.sum() else None,
            "recall": float(inter / t.sum()) if t.sum() else None}


def _center(geometry: dict) -> tuple[float, float]:
    if geometry["type"] == "Point":
        return tuple(geometry["coordinates"][:2])
    c = shape(geometry).centroid
    return c.x, c.y


def match_points(detections: list[dict], reference: list[dict], max_m: float = 4.0,
                 reference_radius: str | None = None) -> dict:
    """Pair each detection with the nearest unclaimed reference object.

    a detection may sit anywhere inside a reference crown (a canopy's middle
    isn't the trunk), so the reach is the bigger of max_m and 75% of the
    reference crown's radius. each reference object is claimed once, closest
    pair first, so two detections can't both "find" the same tree.
    """
    pairs = []
    # polygon references (building footprints) are matched by their middle
    where = [_center(r["geometry"]) for r in reference]
    for i, d in enumerate(detections):
        for j, r in enumerate(reference):
            lon, lat = where[j]
            reach = max(max_m, 0.75 * ((r.get("properties") or {}).get(reference_radius) or 0)) if reference_radius else max_m
            dist = meters((d["lon"], d["lat"]), (lon, lat))
            if dist <= reach:
                pairs.append((dist, i, j))
    claimed_d, claimed_r, matches = set(), set(), []
    for dist, i, j in sorted(pairs):
        if i in claimed_d or j in claimed_r:
            continue
        claimed_d.add(i)
        claimed_r.add(j)
        matches.append({"detection": i, "reference": j, "distance_m": round(dist, 2)})
    return {"matches": matches,
            "new": [i for i in range(len(detections)) if i not in claimed_d],
            "missed": [j for j in range(len(reference)) if j not in claimed_r],
            "precision": len(matches) / len(detections) if detections else None,
            "recall": len(matches) / len(reference) if reference else None}
