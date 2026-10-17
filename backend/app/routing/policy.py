"""Pure policy, independent of geography and HTTP."""
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class Candidate:
    path: tuple[object, ...]
    duration_s: float
    sun_s: float | None
    unknown_s: float


def recommended_detour_fraction(temp_c: float) -> float:
    if not isfinite(temp_c):
        raise ValueError("Temperature must be finite")
    return .35 * min(1.0, max(0.0, (temp_c - (65-32)*5/9) / ((90-65)*5/9)))


def shade_weight(temp_c: float) -> float:
    """Dimensionless penalty on sun seconds; heuristic, not a medical threshold."""
    return 2.0 * recommended_detour_fraction(temp_c) / .35


def choose_routes(candidates: list[Candidate], temp_c: float) -> dict[str, Candidate]:
    if not candidates:
        raise ValueError("Need at least one valid pedestrian path")
    fastest = min(candidates, key=lambda c: (c.duration_s, c.path))
    if any(c.sun_s is None or c.unknown_s > 0.01 for c in candidates):
        # Never treat missing shade as full shade or zero exposure.
        return {"fastest": fastest, "recommended": fastest, "maximum_shade": fastest}
    recommended_cap = fastest.duration_s * (1 + recommended_detour_fraction(temp_c))
    max_cap = min(fastest.duration_s * 1.6, fastest.duration_s + 720)
    eligible_recommended = [c for c in candidates if c.duration_s <= recommended_cap + 1e-6]
    eligible_max = [c for c in candidates if c.duration_s <= max_cap + 1e-6]
    recommended = min(eligible_recommended, key=lambda c: (c.duration_s + shade_weight(temp_c) * float(c.sun_s), c.duration_s, c.path))
    maximum = min(eligible_max, key=lambda c: (float(c.sun_s), c.duration_s, c.path))
    return {"fastest": fastest, "recommended": recommended, "maximum_shade": maximum}
