# VisionLab: see what's there, measure it, find what's missing

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Agent name:** `visionlab`
**Agent address:** `agent1qf0kxk6uevd2hq98lsxtdzn6wgv7dphk6p6jn22kmp5e3jh9u7yc78k2j9e`
**Protocol:** Agent Chat Protocol (ACP), through an Agentverse mailbox, usable from [ASI:One](https://asi1.ai)

VisionLab is a **vision agent that turns images into data you can use**. Tell it what to look for and where. It gets the imagery, **detects and outlines** what you asked for (trees, buildings, water, lawns, shadows, or anything you teach it), and returns **polygons and measurements as structured JSON**.

What makes it more than a detector: it **compares what it sees with real datasets** and reasons about the difference. It says what a dataset already has, what it's **missing**, and it **predicts the values nobody measured**, such as a tree's height from its crown or a building's height from its roof, using relationships it learned from real measurements. Each request is a multi-step workflow: finding the place → imagery → trained models → shapes → comparison → prediction → report.

## Use cases

| Who | Ask VisionLab | What they get |
|---|---|---|
| **Cities and climate teams** | "Map the tree canopy around Main St and compare it with our tree inventory" | Canopy polygons, trees missing from the inventory, and the hot, unshaded streets to plant first |
| **Wildfire safety** (homeowners, insurers, fire departments) | "Classify the land cover around 123 Oak Rd" | Roofs and the vegetation around them as polygons: what grows within the defensible-space zone |
| **Solar and real estate** | "Find the buildings near this address" | Roof outlines with area and an estimated height, for solar sizing or property surveys |
| **Mapping and OpenStreetMap** | "Compare buildings here with this dataset" | Buildings in the photo that are missing from a map, ready to add |
| **Water and flooding** | "Where is the water within 500 m of this point?" | Water polygons from the near-infrared band, to check against a flood map |
| **Your own target** | "Train solar panels from https://…/examples.geojson" | A new detector learned from your examples, ready to find them anywhere |

**Shady Business** (a UCLA walking app that picks shaded routes) is its first real deployment. More on that below.

## What it can do

- **Detect and outline:** tree canopy, buildings/roofs, vegetation, water and shadow, plus a full **land-cover map** (trees, lawn, roofs, water, ground in shade, ground in sun) in one request.
- **Measure:** area, share of the area, individual tree crowns, and estimated heights.
- **Compare:** against any point or polygon dataset you name. It reports what matched, what's new (missing from the dataset), what the dataset has that it didn't see, and areas the dataset never covered.
- **Predict missing data:** heights and sizes from relationships learned from measured data, each with its measured error.
- **Learn:** a new target from labeled GeoJSON examples, trained in about a minute.
- **Works anywhere in the US:** USDA NAIP aerial imagery (0.6 m, colour plus near-infrared, public domain). Places can be addresses, landmarks or coordinates.

## How accurate it is (tested on areas it never trained on)

| Model | Trained on | Held-out result |
|---|---|---|
| Building / roof | 150 OpenStreetMap footprints, UCLA | **IoU 0.54, precision 0.80** |
| Tree canopy | 12,869 measured trees over 64 tiles (UCLA ArborPro inventory), tested on 22 unseen tiles / 3,550 trees | **IoU 0.35 vs 0.26** for the standard vegetation index; precision 0.44 vs 0.32 |
| Tree height from crown | 12,869 measured trees | mean error 4.3 m |
| Building height from roof size | 150 buildings with heights | mean error 6.5 m (8.5 m when guessing) |

## Case study: filling a city dataset's gaps

Shady Business routes people along shaded paths, but its tree inventory and building heights covered only central campus. Walks to the dorms on the hill and the medical center were **27–59% "unknown"**, so the router couldn't offer any shadier choice. VisionLab scanned **every walkway tile outside that area (321 aerial tiles, 89 s)**. It checked each crown it found against UCLA's wider tree inventory: **1,667 matched an inventory tree** (the measured height is kept), **9,246 inventory trees** came in with their measurements, and **12,843 trees plus 3,413 buildings** that no dataset had were added with estimated heights. The router then re-ran identical walks (1 PM, 90°F):

| Walk | Unknown before → after | Route choices | Shadiest option |
|---|---|---|---|
| Rieber Hall → Powell Library | 41% → **0%** | 1 → **3** | 69% shade |
| Hedrick Hall → Powell Library | 55% → **0%** | 1 → **3** | 68% shade |
| Center for Health Sciences → Powell Library | 29% → **0%** | 1 → **3** | 82% shade |
| Drake Stadium → Royce Hall | 27% → **0%** | 1 → **3** | 68% shade |
| Bruin Plate → Royce Hall | 31% → **0%** | 1 → **3** | 68% shade |
| Jacaranda Court → Ackerman Union | 59% → **0%** | 1 → **3** | 76% shade |
| De Neve Plaza → Ackerman Union | 42% → **0%** | 1 → **2** | 59% shade |
| Olympic Hall → Royce Hall | 45% → **0%** | 1 → **2** | 58% shade |

Average unknown on the fastest path: **41% → 0%** across all eight.

All added values are labeled as VisionLab estimates; measured data always takes priority.

**Checked from the street.** Aerial photos see canopy from above, so VisionLab also checks its maps against what a person walking there sees. For the filled tiles it pulled **24 Mapillary street photos over 10 tiles** and measured each photo's **green view index** (the share of the view that is vegetation, the standard urban-forestry measure). Tiles that VisionLab mapped as greener from above were greener from the street too: **correlation 0.65** between the two.

## Run it

```powershell
python -m venv agents\.venv
agents\.venv\Scripts\python -m pip install uagents numpy scikit-learn scikit-image pillow shapely astral pytest
Add-Content mobile\.env "VISIONLAB_SEED=<long random phrase>"   # the agent's identity, keep it secret
agents\.venv\Scripts\python agents\vision\train.py --target tree_canopy --labels backend\data\ucla_trees_campus.geojson --min-objects 25 --radius-property crown_radius_m --baseline vegetation --heights
agents\.venv\Scripts\python agents\vision\train.py --target building --labels backend\data\ucla_buildings.geojson --tile-size 200
agents\.venv\Scripts\python agents\vision\agent.py
agents\.venv\Scripts\python -m pytest agents\vision\tests
```

On first start, open the printed **Agent Inspector** link, sign in to Agentverse and choose **Connect → Mailbox**; then chat from [asi1.ai](https://asi1.ai). To fill a dataset's gaps along walks: `agents\vision\fill_gaps.py --route <from> <to>`, or everywhere with `--everywhere --inventory <wider inventory>`. To compare routes before and after: `agents\vision\benchmark_routes.py`.

## How it's built

- **Imagery:** NAIP via Microsoft Planetary Computer (free, no key), cached locally
- **Features:** colour, near-infrared, vegetation, water and shadow indices, and texture and edges at three scales, per pixel
- **Models:** gradient-boosted pixel classifiers trained from labeled examples, plus built-in spectral models
- **Shapes:** masks → polygons; canopy → individual crowns (distance transform plus watershed)
- **Comparison and prediction:** matching against reference datasets; height models learned from measurements, each scored on held-out data
- **Agent:** uAgents and the Agent Chat Protocol over an Agentverse mailbox; tool failures come back as clear messages
- **Tests:** offline tests for every building block (`tests/`)

## Data and licenses

- **Imagery:** USDA NAIP, public domain.
- **Places and buildings:** © OpenStreetMap contributors (ODbL).
- **Tree inventory:** UCLA ArborPro, used locally for training and comparison only.
