"""What the model sees at each pixel: colour, near infrared, a few standard indices, and texture."""
import numpy as np
from scipy import ndimage

NAMES = ["red", "green", "blue", "nir", "ndvi", "ndwi", "brightness", "excess_green", "blue_share",
         "mean_ndvi_3m", "std_brightness_3m", "mean_ndvi_9m", "std_brightness_9m", "std_nir_3m",
         "mean_brightness_18m", "std_brightness_18m", "edge_9m"]


def indices(pixels: np.ndarray) -> dict[str, np.ndarray]:
    r, g, b, n = (pixels[..., i].astype(np.float32) for i in range(4))
    eps = 1e-6
    return {
        # vegetation reflects near infrared strongly and absorbs red, which is
        # why ndvi separates plants from everything else better than colour does
        "ndvi": (n - r) / (n + r + eps),
        # water is the reverse: bright in green, dark in near infrared
        "ndwi": (g - n) / (g + n + eps),
        "brightness": (r + g + b) / 3,
        "excess_green": 2 * g - r - b,
        # shadows are lit by blue sky instead of the sun, so they lean blue
        "blue_share": b / (r + g + b + eps),
    }


def _local(values: np.ndarray, size_px: int) -> tuple[np.ndarray, np.ndarray]:
    mean = ndimage.uniform_filter(values, size_px)
    square = ndimage.uniform_filter(values * values, size_px)
    return mean, np.sqrt(np.maximum(square - mean * mean, 0))


def pixel_features(pixels: np.ndarray, meters_per_pixel: float) -> np.ndarray:
    """height x width x len(NAMES), float32.

    texture is the part that tells a tree from a lawn: both are green with
    high ndvi, but a crown is lumpy (bright sunlit leaves next to dark gaps)
    and grass is smooth. it's measured at two sizes, a few meters and a crown.
    """
    idx = indices(pixels)
    small = max(3, round(3 / meters_per_pixel))
    large = max(5, round(9 / meters_per_pixel))
    mean_ndvi_s, _ = _local(idx["ndvi"], small)
    _, std_bright_s = _local(idx["brightness"], small)
    mean_ndvi_l, _ = _local(idx["ndvi"], large)
    _, std_bright_l = _local(idx["brightness"], large)
    _, std_nir_s = _local(pixels[..., 3].astype(np.float32), small)
    # a roof is a big smooth patch with straight edges, a plaza is smooth too
    # but not raised, so the wider context (18 m) and how much edge there is
    # nearby help tell buildings from paving
    widest = max(9, round(18 / meters_per_pixel))
    mean_bright_w, std_bright_w = _local(idx["brightness"], widest)
    edges = np.hypot(ndimage.sobel(idx["brightness"], 0), ndimage.sobel(idx["brightness"], 1))
    edge_density = ndimage.uniform_filter(edges, large)
    stack = [pixels[..., i].astype(np.float32) for i in range(4)] + [
        idx["ndvi"], idx["ndwi"], idx["brightness"], idx["excess_green"], idx["blue_share"],
        mean_ndvi_s, std_bright_s, mean_ndvi_l, std_bright_l, std_nir_s,
        mean_bright_w, std_bright_w, edge_density]
    return np.dstack(stack).astype(np.float32)
