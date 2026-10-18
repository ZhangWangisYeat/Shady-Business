"""Pixel models: built-in spectral experts that need no training, and a classifier that learns from examples."""
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from skimage.filters import threshold_otsu

from visionlab.features import NAMES, indices, pixel_features
from visionlab.imagery import Tile

MODELS = Path(__file__).resolve().parents[1] / "data" / "models"


# the built-in experts are standard remote-sensing rules. they work anywhere
# naip does, with no examples, and they're the baseline a trained model has
# to beat (the evaluation reports both).
def vegetation(tile: Tile) -> np.ndarray:
    return (indices(tile.pixels)["ndvi"] > 0.15) & tile.valid


def water(tile: Tile) -> np.ndarray:
    return (indices(tile.pixels)["ndwi"] > 0.2) & tile.valid


def shadow(tile: Tile, exclude: np.ndarray | None = None) -> np.ndarray:
    """Shadowed open surface: the dark cluster of what isn't vegetation.

    a fixed brightness cut fails between images (exposure, season, haze), so
    the cut is otsu's threshold on this tile's own non-vegetation pixels.
    """
    bright = indices(tile.pixels)["brightness"]
    pool = tile.valid & ~(exclude if exclude is not None else vegetation(tile))
    if pool.sum() < 50:
        return np.zeros(tile.shape, bool)
    cut = threshold_otsu(bright[pool])
    return pool & (bright < min(cut, 110))


EXPERTS = {"vegetation": vegetation, "water": water, "shadow": shadow}


@dataclass
class PixelModel:
    """Learns one feature (tree canopy, roofs, solar panels...) from labeled tiles."""
    target: str
    classifier: HistGradientBoostingClassifier | None = None
    threshold: float = 0.5
    trained_on: dict = field(default_factory=dict)

    def fit(self, tiles: list[Tile], masks: list[np.ndarray], ignore: list[np.ndarray] | None = None,
            samples_per_tile: int = 40_000, seed: int = 0) -> "PixelModel":
        rng = np.random.default_rng(seed)
        xs, ys = [], []
        for i, (tile, mask) in enumerate(zip(tiles, masks)):
            feats = pixel_features(tile.pixels, tile.meters_per_pixel)
            usable = tile.valid & ~(ignore[i] if ignore else False)
            pos, neg = np.flatnonzero(usable & mask), np.flatnonzero(usable & ~mask)
            # equal numbers of both classes, so a mostly-empty tile doesn't
            # teach the model that the answer is almost always "no"
            take = min(samples_per_tile // 2, len(pos), len(neg))
            if take == 0:
                continue
            chosen = np.concatenate([rng.choice(pos, take, replace=False), rng.choice(neg, take, replace=False)])
            xs.append(feats.reshape(-1, len(NAMES))[chosen])
            ys.append(mask.reshape(-1)[chosen])
        if not xs:
            raise ValueError("No tile had both examples and non-examples to learn from")
        x, y = np.concatenate(xs), np.concatenate(ys)
        self.classifier = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, max_leaf_nodes=31,
                                                         l2_regularization=1.0, random_state=seed)
        self.classifier.fit(x, y)
        self.trained_on = {"tiles": len(xs), "pixels": int(len(y)), "positive_share": float(y.mean())}
        return self

    def probability(self, tile: Tile) -> np.ndarray:
        feats = pixel_features(tile.pixels, tile.meters_per_pixel)
        p = self.classifier.predict_proba(feats.reshape(-1, len(NAMES)))[:, 1]
        return np.where(tile.valid, p.reshape(tile.shape), 0.0)

    def predict(self, tile: Tile) -> np.ndarray:
        return self.probability(tile) >= self.threshold

    def save(self, folder: Path = MODELS) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.target}.pkl"
        path.write_bytes(pickle.dumps(self))
        return path

    @staticmethod
    def load(target: str, folder: Path = MODELS) -> "PixelModel":
        path = folder / f"{target}.pkl"
        if not path.exists():
            raise FileNotFoundError(f"No trained model called {target!r}; train one first")
        return pickle.loads(path.read_bytes())

    @staticmethod
    def available(folder: Path = MODELS) -> list[str]:
        return sorted(p.stem for p in folder.glob("*.pkl")) if folder.exists() else []
