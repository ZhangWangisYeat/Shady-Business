"""Environment-only settings; no credentials or network requests at import time."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
GRAPH_FILE = Path(os.getenv("SHADY_GRAPH_FILE", str(ROOT / "data" / "ucla_walk.graphml")))
SHADE_FILE = Path(os.getenv("SHADY_SHADE_FILE", str(ROOT / "data" / "ucla_buildings.geojson")))
TREE_FILE = Path(os.getenv("SHADY_TREE_FILE", str(ROOT / "data" / "ucla_trees.geojson")))
CAMPUS_CENTER = (-118.4452, 34.0689)  # map viewport only; not a verified point of interest
MAX_SNAP_METERS = 170.0
