#!/usr/bin/env python3
"""Step 3 (network): ask Gemini to map trees, ground shade and buildings in each fetched photo.

Needs GEMINI_API_KEY (free from aistudio.google.com/apikey). One photo per call,
answers cached per photo, so re-running only pays for photos not done yet.
Free-tier note: Google may use free-tier prompts and images to improve its
products, which is fine for public Mapillary/USGS photos but not for anything private.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.vision.gemini import DEFAULT_MODEL, Budget, QuotaReached, build_request, parse_response  # noqa: E402
from app.vision.keys import load_keys  # noqa: E402

VISION = ROOT / "backend/data/vision"
PROMPT_VERSION = 1  # bump when the prompt changes, so old answers get redone


def main():
    load_keys()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-network", action="store_true", help="I authorize calls to the Gemini API free tier")
    parser.add_argument("--dry-run", action="store_true", help="show what would be sent, without calling Gemini")
    parser.add_argument("--max-calls", type=int, default=20, help="hard cap on Gemini calls this run")
    parser.add_argument("--min-interval", type=float, default=7.0, help="seconds between calls (7 s stays under 10 a minute)")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--thinking-budget", type=int, default=512)
    parser.add_argument("--only", choices=["aerial", "street"], help="just one kind of photo")
    args = parser.parse_args()

    if not (VISION / "photos.json").exists():
        raise SystemExit("No photos.json yet: run scripts/vision_fetch_images.py first.")
    photos = json.loads((VISION / "photos.json").read_text(encoding="utf-8"))
    out_dir = VISION / "detections"
    out_dir.mkdir(parents=True, exist_ok=True)
    def done(photo):
        path = out_dir / f"{photo['id']}.json"
        return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("prompt_version") == PROMPT_VERSION
    # aerial first: one aerial tile places every crown on the map, a street
    # photo only guesses distance, so if the budget runs out the best is done
    todo = sorted((p for p in photos if not done(p) and (not args.only or p["kind"] == args.only)),
                  key=lambda p: p["kind"] != "aerial")
    print(f"{len(todo)} photos to analyze, up to {args.max_calls} calls with {args.model}.")
    if args.dry_run or not todo:
        for photo in todo[:args.max_calls]:
            print(f"  would send {photo['kind']:6s} {photo['id']} ({(VISION / photo['file']).stat().st_size // 1024} KB)")
        if todo:
            print("\nFirst prompt:\n" + build_request(b"", "image/jpeg", todo[0], args.thinking_budget)["contents"][0]["parts"][0]["text"])
        return
    if not args.confirm_network:
        raise SystemExit("Pass --confirm-network to call Gemini (or --dry-run to preview).")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("Set GEMINI_API_KEY first (see docs/vision-pipeline.md).")

    budget = Budget(args.max_calls, args.min_interval)
    tokens = 0
    for photo in todo:
        body = build_request((VISION / photo["file"]).read_bytes(), photo["mime"], photo, args.thinking_budget)
        try:
            response = budget.call(key, args.model, body)
        except QuotaReached as exc:
            print(f"Stopping: {exc}. Re-run later; finished photos are kept.")
            break
        except RuntimeError as exc:
            print(f"  {photo['id']}: {exc}", file=sys.stderr)
            continue
        try:
            detections = parse_response(response, photo["kind"])
        except ValueError as exc:
            print(f"  {photo['id']}: {exc}", file=sys.stderr)
            continue
        used = sum(v or 0 for v in detections["tokens"].values())
        tokens += used
        detections.update(photo_id=photo["id"], kind=photo["kind"], model=args.model, prompt_version=PROMPT_VERSION,
                          analyzed_at=datetime.now(timezone.utc).isoformat())
        (out_dir / f"{photo['id']}.json").write_text(json.dumps(detections, indent=2), encoding="utf-8")
        print(f"  {photo['kind']:6s} {photo['id']}: {len(detections['trees'])} trees, "
              f"{len(detections['buildings'])} buildings, {used} tokens")
    print(f"Used {budget.used} calls and about {tokens} tokens.")


if __name__ == "__main__":
    main()
