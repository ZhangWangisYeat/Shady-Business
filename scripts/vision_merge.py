#!/usr/bin/env python3
"""Step 5 (offline): build a new tree file = inventory + accepted vision trees, for the shade model.

Never overwrites the inventory. Point the backend at the result with
SHADY_TREE_FILE, restart it, and routes pick the new trees up. Vision trees
are estimates, so this needs --confirm-estimated.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.shade.trees import read_tree_model  # noqa: E402
from app.vision.compare import merged_tree_file  # noqa: E402

VISION = ROOT / "backend/data/vision"
TREES = ROOT / "backend/data/ucla_trees.geojson"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-estimated", action="store_true",
                        help="I understand the added trees are unverified Gemini estimates")
    parser.add_argument("--extend-coverage", action="store_true",
                        help="also count analyzed aerial tiles as covered ground (a claim that every tree there was found)")
    parser.add_argument("--trees", type=Path, default=TREES)
    parser.add_argument("--out", type=Path, default=ROOT / "backend/data/ucla_trees_vision.geojson")
    args = parser.parse_args()
    if not args.confirm_estimated:
        raise SystemExit("Pass --confirm-estimated: vision trees are estimates, not inventory measurements.")
    if args.out.resolve() == args.trees.resolve():
        raise SystemExit("Refusing to overwrite the inventory itself; pick another --out.")

    inventory = json.loads(args.trees.read_text(encoding="utf-8"))
    candidates = json.loads((VISION / "candidates.geojson").read_text(encoding="utf-8"))
    aerials = [p for p in json.loads((VISION / "photos.json").read_text(encoding="utf-8")) if p["kind"] == "aerial"
               and (VISION / "detections" / f"{p['id']}.json").exists()]
    merged = merged_tree_file(inventory, candidates, aerials, args.extend_coverage)
    args.out.write_text(json.dumps(merged), encoding="utf-8")
    # load it the way the server will, so a bad file fails here and not mid-demo
    dataset = read_tree_model(args.out)
    added = merged["metadata"]["vision_supplement"]["added_trees"]
    print(f"Wrote {args.out.relative_to(ROOT)}: {len(dataset.trees)} trees ({added} from vision).")
    print(f"Use it:  $env:SHADY_TREE_FILE = \"{args.out}\"  then restart the backend.")
    if not args.extend_coverage:
        print("Coverage unchanged, so new trees only matter inside the existing inventory area. "
              "Outside it, routes stay 'unknown' until buildings there have heights too.")


if __name__ == "__main__":
    main()
