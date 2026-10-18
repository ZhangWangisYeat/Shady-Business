# UCLA local data intake audit — 2026-10-17

## Latest: local tree data connected (supersedes earlier export blocker)

The user directed this feature to use the existing data found in the chat
**查找 UCLA 植被数据**. That chat produced
`arborpro-inspect/ucla_tree_inventory.csv` and `ucla-public.json` in the parent
workspace. This implementation did not repeat the download. It normalized the
existing CSV into ignored `backend/data/ucla_trees.geojson`: 3,623 standing-tree
records with usable dimensions inside the same study rectangle as buildings.
One non-tree record in the rectangle was excluded; 16,553 records were outside.
Status numeric code 1 was cross-checked against Tree in the viewer. No complete
campus boundary, source survey date or public redistribution license is inferred.

Tree projection, combined default loading and HTTP segment scoring are now
implemented and verified with **96 backend tests** plus a real-data API check.
See `../tree-shade-integration.md`. The details below describe the earlier
investigation; the CSV/input absence is no longer a blocker for local modeling.

## Repository inspection

Read-only GitHub ref inspection and fetch found `main` and `Backend-APIs`, both at
`e23870badc85a9e5794db55569423af939b78081`. Neither contains building footprint or
measured-tree assets. `backend/data/` is intentionally ignored except its README.
The tracked `cache/ddfda28b428dc269c2b3bc9ff364bd48c7f46420.json` is an Overpass
response with 25,756 nodes and 5,725 ways. There are no `building` features and
no `natural=tree` features in it; it does not supply a shade dataset.

## Existing local OSM source

The earlier workspace (outside the cloned repository) contains `data/ucla_osm.json`.
Its metadata identifies OpenStreetMap contributors / ODbL 1.0, fetch timestamp
`2026-10-17T01:21:13.954658+00:00`, bbox `[-118.448, 34.0675, -118.438, 34.0755]`.
It is a partial central-campus extraction, not verified complete UCLA coverage.

| Contents | Count | Intake |
| --- | ---: | --- |
| Building footprints with OSM height tags | 134 | Use as unverified geometry estimates |
| Building heights estimated from levels | 3 | Preserve footprint; set runtime height unknown |
| Buildings with assumed default 12 m height | 16 | Preserve footprint; set runtime height unknown |
| Tree points buffered with assumed 4 m crown radius | 175 | Exclude from measured canopy/shadow inputs |
| Woodland polygons without measured crown heights | 2 | Exclude from timed tree-shadow inputs |

`scripts/import_osm_buildings.py` imports this bundle offline, records original
SHA-256, source, license, coordinate/height units and fetch timestamp. It preserves
all 153 building outlines and supplies 134 usable OSM-tagged height estimates to
the model. It does not fabricate survey dates or complete coverage.

Reproduce the local import from the clone root:

```powershell
python scripts/import_osm_buildings.py --input ../data/ucla_osm.json --out backend/data/ucla_buildings.geojson
```

The generated file is ignored by Git. It is loaded by the current default
`SHADY_SHADE_FILE` path. After importing, a running API process must restart or
clear its cached model. New precise segment scoring is independently callable;
the route service still needs its coordinated scoring integration. Existing
source-cache inputs are not automatically committed, distributed or uploaded.

The local model successfully loaded 134 buildings and produced a nonempty shadow
union for `2026-10-17T15:00:00-07:00`. Scoring one actual source edge returned
unknown exposure rather than false sunshine where the coverage was unverified.
This confirms import/scoring plumbing, not field accuracy or full app integration.

## Tree data still needed

Preferred source: UCLA's [official tree inventory entry point](https://sustain.ucla.edu/landscape-and-biodiversity/)
and [ArborPro viewer](https://app.arborprousa.com/viewer/7q07Ea8G2uVSf6KR/legacy_tree/ku2laqgzx6).
The [2025 management plan](https://sustain.ucla.edu/wp-content/uploads/2025/07/Reduced-Size-Final-UCLA-Urban-Forest-Management-Plan-July-2025.pdf)
describes the inventory. The browser inspection below supersedes the earlier web
tool failure. A public machine-readable export and downstream reuse permission
have NOT been established; no unsupported endpoint was scraped.

### Public viewer verified in browser

The supplied detail URL loads after an initial loading delay. The actual
`Open Inventory View` table exposes these field names:

| Viewer field | Planned normalized field | Conversion |
| --- | --- | --- |
| `Tree ID` | `tree_id` | Preserve identifier |
| `Latitude`, `Longitude` | WGS84 Point | Store `[longitude, latitude]` |
| `Height (feet)` | `height_m` | Multiply by 0.3048 |
| `Crown (feet)` | `crown_radius_m` | If confirmed crown spread, multiply by 0.3048 / 2 |
| `Status` | tree presence/status | Exclude stumps/vacancies from live-tree modeling |
| `Botanical`, `Common` | species labels | Preserve source labels |

The table reports **20,177 records**. Its displayed rows include geographically
off-campus locations, so the full inventory cannot be treated as main-campus
coverage. The public detail panel also exposes height/crown values. The public
table does not show live crown ratio or source measurement dates among its
displayed columns; neither is inferred.

The official plan (PDF page 18) describes crown spread as horizontal extent,
typically measured at its widest point, supporting the diameter/spread mapping
rather than using the displayed value as a radius. Confirm column semantics in
the exported file before importing.

Opening the inventory panel revealed pagination and sortable columns but no
visible `Report` or `Export CSV` control. The public header exposed share, legend,
layer settings and reset. The [vendor FAQ](https://arborprousa.com/faq/) documents
`Reporting → Export CSV` and `Open Inventory View → Report` for supported account
interfaces; their availability in this public share is unverified. The browser
session was lost during a further layer-menu inspection; no export was obtained.
Do not interpret the absent observed button as proof that no permitted export
can ever be enabled. Ask the inventory owner for its supported CSV export or
access to the appropriate export feature, plus downstream model-use permission.

No tree records or photographs were exported/committed and no tree dataset is
claimed to be loaded. The repository's `AGENTS.md` specifically requires supported
viewer controls and reuse authorization before exporting/committing inventory data.

Minimum file: CSV/GeoJSON with tree ID, WGS84 longitude/latitude (or explicit CRS),
tree height, crown spread/diameter or radius with the convention identified, and
explicit units. Also provide source/date and permission for model use; whether
raw data may be published on GitHub is a separate question. If available, include
live crown ratio/crown base height, presence/status (live tree vs stump/vacancy)
and current measurements. Start with trees along a central-campus demonstration
corridor rather than requiring the entire inventory.

An alternative is a properly georeferenced canopy polygon/raster plus canopy
elevation/height data (e.g., DSM and DTM); a binary canopy mask alone does not
provide time-dependent crown shadows. No fixed 4 m radius will be promoted to
measured crown spread. The existing `scripts/normalize_ucla_trees.py` can convert
permissioned CSV heights and spread to meters once the columns are available.

The county building service is not substituted: its [official metadata](https://public.gis.lacounty.gov/arcgis/rest/services/DRP/GISNET_Public/MapServer/434/iteminfo)
still specifies `LARIAC Members only`. This audit did not download that dataset.
No paid API or GitHub write access is required for the next tree-data intake step.
