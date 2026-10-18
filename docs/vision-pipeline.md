# Vision pipeline: filling tree-inventory gaps with Gemini

Gemini looks at photos of places the tree inventory doesn't cover. It maps tree crowns, ground shade/sun and buildings as strict JSON. The pipeline puts those on the map, compares them with the inventory, and can write a **new** tree file that the existing shade model loads. Gemini is not trained or fine-tuned here: it's prompted, with a fixed JSON schema and temperature 0. Every number it gives is an estimate and is labeled as one.

```
1 find gaps (offline) → 2 fetch photos (USGS + Mapillary) → 3 Gemini (one call per photo, cached)
→ 4 compare with inventory (offline) → 5 merge into a new tree file (offline) → SHADY_TREE_FILE
```

Code: `backend/app/vision/` (geo, gaps, gemini, compare) and `scripts/vision_*.py`. Tests: `backend/tests/test_vision.py` (offline). Everything the pipeline writes goes into `backend/data/vision/`, which is gitignored.

## Where the gaps are (2026-10-18)

- The inventory (ArborPro, 3,623 trees) and the building heights both cover only the rectangle `-118.448, 34.0675, -118.438, 34.0755`.
- 217 of the 397 route places are outside it, grouped into 42 sites: the Hill (Olympic Hall is 524 m from the nearest known tree, Bruin Plate 183 m), Drake Stadium, Spieker and the medical side. One site inside the rectangle has almost no trees (Intramural Field, the Bike Shop and Parking 7), probably because it's open ground.
- **Do this first:** the ArborPro source had 16,553 more trees outside the rectangle, left out only by the import bbox. Re-running `scripts/import_arborpro_trees.py` with a wider `--bbox` adds *measured* trees there, which beats any vision estimate. The CSV isn't on this machine; ask whoever ran the import.
- **Trees alone don't light up the Hill.** A route segment only counts as known where *both* the tree and building files cover it. Outside the rectangle, routes stay "unknown" until buildings there have heights too. The pipeline already asks Gemini for building heights from shadows, but merging those into the building file is a separate step that isn't written yet.

## What you need

| | Where | Cost |
|---|---|---|
| `MAPILLARY_TOKEN` | mapillary.com/dashboard/developers → register an app → copy the **client token** (starts `MLY\|`) | free |
| `GEMINI_API_KEY` | aistudio.google.com/apikey → Create API key (no billing needed for the free tier) | free tier |
| aerial photos | USDA NAIP 0.6 m via Microsoft Planetary Computer, no key | free, public domain |

Set them for the current PowerShell window only, never in a committed file:

```powershell
$env:MAPILLARY_TOKEN = "MLY|..."
$env:GEMINI_API_KEY  = "..."
```

**Free-tier limits.** For `gemini-2.5-flash` they were about 10 requests a minute and 250 a day when this was written; check aistudio.google.com/rate-limit for yours.
- The pipeline sends one photo per call, waits 7 s between calls, stops at `--max-calls` (default 20), and stops outright on the first 429.
- Answers are cached per photo, so re-running only pays for new photos.
- The default run is at most 24 photos, so at most 24 calls.
- On the free tier, Google may use prompts and images to improve its products. That's fine for public USGS/Mapillary photos; don't send anything private.

## Step by step

Run from the repo root with the backend venv (`backend\.venv\Scripts\python`).

**1. Find gap sites** (offline). `--focus` puts a place first, and `--route` also samples the walk between two place ids:
```powershell
backend\.venv\Scripts\python scripts/vision_find_gaps.py --focus "Olympic Hall" --route olympic-hall royce-hall --every 120 --limit 8
```
→ `backend/data/vision/gaps.json`. Check the list; each site costs up to 4 photos.

**2. Fetch photos.** One aerial tile (140 m) and up to 3 street photos per site, facing different directions, are fetched, up to 24 photos in all:
```powershell
backend\.venv\Scripts\python scripts/vision_fetch_images.py --confirm-network --per-site 3 --max-photos 24
```
→ `photos/` and `photos.json` with source, license and attribution for each photo. The USGS export is slow and sometimes returns 504; the script tries twice and then carries on with street photos. Without a Mapillary token you get only aerial tiles.

**3. Preview, then ask Gemini:**
```powershell
backend\.venv\Scripts\python scripts/vision_detect.py --dry-run
backend\.venv\Scripts\python scripts/vision_detect.py --confirm-network --max-calls 5
```
- The dry run sends nothing; it prints the queue and the first prompt.
- Start with 5 calls and look at the results in `detections/*.json` before spending more.
- Aerial photos go first, because they place crowns on the map most accurately.
- `--only aerial`, `--model`, `--thinking-budget` and `--min-interval` adjust a run.

**4. Compare with the inventory** (offline):
```powershell
backend\.venv\Scripts\python scripts/vision_compare.py --min-confidence 0.6
```
This writes:
- **`candidates.geojson`**: every detected tree. `status: "tree"` means accepted into the shade model; `"vision_review"` means it waits for a person.
- **`ground.geojson`**: shade/sun patches at photo time.
- **`report.json`**: counts, plus Gemini's median height error on trees the inventory already measured. That error is the best single check on whether to trust its new trees.

Drag the `.geojson` files onto geojson.io to look at them on a map.

A tree is accepted only if it's a single tree (not a shrub, and not a canopy Gemini couldn't split, with radius up to 12 m), has a height, reaches the confidence threshold, and isn't already in the inventory. Repeat sightings across photos merge, and aerial positions win over street-level guesses.

**5. Merge into a new tree file** (offline; never overwrites the inventory):
```powershell
backend\.venv\Scripts\python scripts/vision_merge.py --confirm-estimated
$env:SHADY_TREE_FILE = "$PWD\backend\data\ucla_trees_vision.geojson"
```
Restart the backend, and routes then use the added trees. `--extend-coverage` also counts the analyzed aerial tiles as covered ground. That's a claim that every tree there was found, so use it only after looking at the tiles. It still won't make Hill routes known until the buildings there have heights too.

## How the prompts work

- **Aerial:** the north-up tile, its size and center, and a 0–1000 grid. Gemini returns crown outlines (6–16 points), kind, height from crown size and shadow length, and confidence. It also returns ground patches labeled shade/sun, and roof outlines with heights. Grid points convert to map coordinates exactly (Web Mercator), so crowns land within a couple of meters.
- **Street:** the camera position, compass heading and field of view (from Mapillary's focal length, or 70°), plus the grid. Gemini returns a box per tree, the trunk column, distance, height and crown width, plus how much of the ground is in shade. Position comes from heading plus distance, so the uncertainty is about 25% of the distance (at least 3 m). Trees further than 60 m are dropped.
- Ground shade/sun is only true at the moment of the photo, so it's stored for checking our model, never used as route shade. Route shade always comes from the shade model casting the trees' shadows for the actual walking time.

## Licensing

- **Mapillary:** photos are CC BY-SA 4.0. Every photo and candidate keeps its credit line. Don't commit the photos.
- **USDA NAIP** (via Planetary Computer): public domain. USGS's own NAIP servers timed out and reset connections on 2026-10-18, so the mirror is used.
- **Never used:** Mapbox and Google imagery, per AGENTS.md.
- **The inventory file itself** still carries its own "redistribution unverified" note.
