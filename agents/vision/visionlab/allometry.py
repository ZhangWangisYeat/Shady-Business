"""Predicting a tree's height from its crown width, learned from a measured inventory.

an image taken from straight above shows how wide a crown is but not how tall
the tree is, and the shade model needs a height. trees of a given spread fall
in a fairly narrow height range, so a curve fitted to thousands of measured
trees gives a usable estimate with an honest error bar.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class HeightModel:
    slope: float
    intercept: float
    mae_m: float  # mean absolute error on held-out trees
    within_25pct: float  # share of held-out trees predicted within 25%
    trained_on: int

    def predict(self, crown_radius_m: float) -> float:
        return float(np.exp(self.intercept + self.slope * np.log(max(crown_radius_m, 0.5))))

    @staticmethod
    def fit(heights: list[float], radii: list[float], seed: int = 0) -> "HeightModel":
        """log(height) = a + b * log(radius), checked on a held-out fifth of the trees."""
        h, r = np.asarray(heights, float), np.asarray(radii, float)
        keep = (h > 0) & (r > 0)
        h, r = h[keep], r[keep]
        order = np.random.default_rng(seed).permutation(len(h))
        test, train = order[: len(h) // 5], order[len(h) // 5:]
        b, a = np.polyfit(np.log(r[train]), np.log(h[train]), 1)
        predicted = np.exp(a + b * np.log(r[test]))
        error = np.abs(predicted - h[test])
        # refit on everything once the error has been measured honestly
        b, a = np.polyfit(np.log(r), np.log(h), 1)
        return HeightModel(float(b), float(a), float(error.mean()), float((error <= 0.25 * h[test]).mean()), int(len(h)))
