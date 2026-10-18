# Verified project status — 2026-10-17

## Current workspace: G1 route and bounded candidate search verified

- Downloaded the ignored UCLA OSM walking GraphML through the authorized OSMnx
  script: 3,636 nodes / 9,712 directed walk edges. `/api/health` reports
  `dataset_status=ready`.
- A live Royce Hall → Ackerman request returned a connected 370.35 m / 284.89 s
  Fastest path. With no local shade files, Recommended and Maximum Shade correctly
  alias Fastest and report exposure unknown rather than inventing alternatives.
- Added bounded multi-weight candidate search over exact `(u, v, key)` graph
  edges. Synthetic complete-coverage integration verifies distinct Fastest,
  temperature-aware Recommended and Maximum Shade routes, including the hard
  detour cap. The algorithm is explicitly approximate `candidate_search`, not a
  proof of the globally minimum-sun route.
- Request-scoped edge profiles now score each eligible keyed edge once. Unknown
  side branches are excluded from the shade-search subgraph instead of disabling
  otherwise complete candidates; Fastest must still be completely scored before
  any shade alternative is selected. A regression fixture verifies both distinct
  bounded modes and the unknown-safe gate.
- Added a read-only shade-coverage readiness gate and combined-source runtime
  support. Verified building/tree coverage polygons are intersected; either
  incomplete source keeps exposure unknown. The real Royce→Ackerman bounded
  candidate area contains 622 eligible keyed edges. Its audit now finds all 150
  retained building footprints and all 3,623 trees model-ready, but still exits
  blocked because neither source carries a verified coverage polygon.
- At the user's direction, 16 screenshot-supplied approximate heights were added
  as `user_supplied_estimate`, never as measured/field-verified values. Three
  unnamed OSM roof/tent/shed features were excluded from shade obstruction
  modeling; the pedestrian graph was not altered. The original uploaded GeoJSON
  remains unchanged and the derived runtime file records all overrides/exclusions.
  See `references/demo-corridor-building-gaps.md`.
- An isolated real-graph preview temporarily assumed the shared study rectangle
  was complete **in memory only**; no GeoJSON or API flag was changed. At 09:00
  and 15:00 it produced three distinct Fastest/Recommended/Maximum Shade paths.
  At noon Recommended correctly matched Fastest while Maximum Shade differed;
  at 10 C Recommended also matched Fastest. This verifies route selection, not
  obstruction completeness, and is not a user-visible G3 sign-off.
- A Git-ignored Powell→Ackerman field packet now covers the envelope of all 643
  Maximum Shade-eligible edges (and therefore every Recommended candidate), plus
  the time-specific external shadow buffer. It lists 41 buildings, 1,288 trees
  and 15 route observations. A read-only SHA-256-bound validator fails closed on
  missing/stale evidence and a structural fingerprint prevents candidate-scope
  edits. A separate explicitly confirmed promotion command writes derived files
  only; the current unfilled packet was correctly refused with no output.
- G2/G3 API contract v0.4 now exposes `solar_status`, explicit model-level
  `shade_coverage`, and per-route `coverage_fraction`; the FastAPI response model
  and mobile TypeScript DTO agree. A real Powell→Ackerman 38°C request returned
  HTTP 200 and all three route modes. Because local coverage remains unverified,
  both alternatives truthfully aliased Fastest, `sun_seconds` stayed null and
  route coverage reported 0.8358 rather than claiming complete exposure.
- API failure recovery now uses stable error codes for invalid locations,
  same-node/no-path requests and graph outages. Temporary failures expose retry
  intent without leaking developer setup instructions. A malformed local shade
  dataset degrades to the real Fastest graph path with unknown exposure instead
  of blocking routing; mobile preserves the query and offers retry/change-place
  actions, ignores stale route responses, and distinguishes weak GPS/off-route.
- **120 backend tests pass**. Mobile TypeScript, skill mirrors and whitespace checks pass. The live
  fallback API responded in roughly 63–125 ms after graph load on this machine.
- The supplied ArborPro CSV was normalized locally into 3,623 modeled tree
  crowns. A live 15:00 Royce → Ackerman request produced 16 modeled-shade
  segments before the building dataset was installed. The supplied ODbL
  `ucla_buildings.geojson` now loads 134 explicit, unverified OSM height tags and
  16 user-provided estimates from 150 retained footprints. With buildings and
  trees combined, the same request returns 25
  modeled-shade segments and 11 unknown segments, with conserved duration and
  connected geometry. Combined obstruction coverage remains unverified, so
  distinct real-UCLA shade routes remain **NOT VERIFIED** and all three modes
  correctly alias Fastest. TCP 8000 is also inside this Windows host's reserved
  7940–8139 range; live verification used port 8140 without changing system
  reservations.

## Completed local crown integration (supersedes earlier intake blockers)

- Read the chat **查找 UCLA 植被数据** and used its existing local ArborPro CSV at
  the user's explicit request. No new download or GitHub write was performed.
- Imported 20,177 source rows into the OSM study rectangle: 16,553 outside,
  1 non-tree excluded, **3,623 standing-tree records with usable height/spread**.
  Source coordinates/dimensions/IDs retained with units and SHA-256; no default
  crown radius, survey date or complete coverage invented.
- Building + tree model loads by default (150 buildings, 3,623 crowns), supports
  standalone `--trees`, and supplies precise segments to existing `/api/routes`
  without changing public JSON shape or mobile enums. Crown vertical extent and
  foliage opacity are explicitly approximate; uncovered daylight remains unknown.
- **96 backend tests PASS**, including 32 tree-specific cases and existing
  scoring/import/API/graph/policy tests. Real-data in-memory OSM API checks passed
  at 09:00/12:00/15:00/23:00 with conserved times and connected segment geometry.
  Daytime API calls took about 1.2–1.3 seconds on this machine.
- Dataset files remain Git-ignored. Real source redistribution, complete campus
  coverage, field accuracy and physical-device validation are **NOT VERIFIED**.
  A default GraphML is still not installed in this clone; the real-data API test
  supplied the existing OSM graph in memory, not a running app deployment.
- See `docs/tree-shade-integration.md` for formulas, commands and comparison
  results. Earlier sections below are historical milestones, not current blockers.

## ArborPro public viewer inspection (2026-10-17)

- Supplied UCLA viewer successfully loaded in the browser. Verified actual table
  fields: IDs, latitude/longitude, height/crown in feet, status and species.
  Pagination reports 20,177 records, including off-campus entries.
- Opened inventory panel; no visible Report/Export CSV control found there.
  No export, bulk scrape, restricted endpoint request, or model-use permission
  obtained. Measured tree data is not loaded into the scoring runtime yet.
- Documented observed fields, unit mapping, supported vendor export paths and
  remaining access/permission questions in `docs/references/ucla-data-audit.md`.

## Local data intake slice (2026-10-17, after algorithm slice)

- Read-only remote inspection found `main` and `Backend-APIs` at the same commit;
  tracked Overpass cache has no building/tree obstruction data.
- Imported an existing local ODbL OSM bundle into ignored
  `backend/data/ucla_buildings.geojson`: 153 footprints, 134 unverified OSM height
  tags usable by the model, 19 heights kept unknown. Source SHA-256 and units
  recorded; coverage remains unverified. Actual solar/shadow/scoring smoke passed.
- Excluded 175 fixed-radius tree crowns and 2 woodland polygons from measured
  tree inputs. No measured canopy file or tree-shadow runtime integration yet.
- Full intake findings and remaining tree-data requirements:
  `docs/references/ucla-data-audit.md`. No GitHub write or upload performed.
- Intake verification: **64 backend tests passed**, including 9 new importer
  cases. Direct health check reports `shade_status=modeled` and
  `dataset_status=not_loaded`: buildings are loaded but a routing GraphML is not.
  Skill mirror, staged/unstaged whitespace checks passed; generated building
  data is confirmed ignored by Git. No field or mobile accuracy claim follows.

## Local feature slice: route shade scoring (2026-10-17)

- Local branch `feature/route-shade-scoring`; GitHub has not been pushed or changed.
- Independent scoring algorithm and local JSON command implemented; usage and
  limits in `docs/shade-scoring.md`. Builds exact-intersection ordered road
  segments, separates known sun/shade/unknown/nighttime, conserves supplied edge
  durations, and retains provenance. No public JSON schema or route-policy change.
- Building sweeps preserve concavities/courtyards; overlapping shadows count once.
  Low-angle predictions return unknown rather than silently truncating shadows.
- Verification: **55 backend tests passed** (46 new shade tests and 9 existing
  API/graph/policy tests) on Windows/Python 3.14.2. Skill mirror check and
  `git diff --check` passed. The installed Shapely emitted 79 deprecation
  warnings for the still-compatible `shapely.ops.transform` API; none are test
  failures. FastAPI in-process tests needed the unrestricted local runner because
  its restricted counterpart stalled. Tests made no external provider requests.
- No real building/tree dataset loaded; no field validation, mobile integration,
  or G2 sign-off. Runtime route service still uses its legacy shade adapter.

## Verified in creation environment
- GitHub-ready directory structure; five canonical portable skills and mirror script.
- FastAPI `/api/health`, `/api/places`, `/api/routes` source code; no hidden mock route fallback.
- Backend policy, graph fixture and API tests: **9 passed** using locally available Python packages.
- Python source syntactically valid; unit tests run without network requests.

## NOT verified / NOT complete
- No downloadable campus OpenStreetMap graph in the ZIP; the route endpoint returns HTTP 503 until fetched.
- Campus POI coordinates need on-the-ground / map verification.
- **New source discovery:** UCLA’s 2025 Urban Forest Management Plan confirms a 2023–2024 field inventory that includes tree height and crown spread. Public ArborPro viewer linked. Also verified county 2024 canopy raster and 2023 building layer with HEIGHT field. **No data were downloaded, licensed for reuse, or ingested into a model.** Building layer metadata states LARIAC Members only; see source catalog.
- No building-height/tree-crown geodata installed in the app; sunlight remains `unknown` until processing/field validation.
- Native Expo / Mapbox dependency installation, Metro build, device rendering and GPS have not been run.
- Algorithm currently searches k shortest travel paths, not all Pareto-optimal shade paths.
- First-person perspective means pitched camera-following map, not Street View; full voice turn-by-turn not implemented.
- GPS off-route/arrival matching is a first-pass prototype requiring smoothing/hysteresis and field testing.

## Focus before tomorrow's hacking
1. Keep frontend/backend **as a template**; avoid refactoring working scaffolds tonight.
2. Open UCLA’s public ArborPro viewer and look for an allowed CSV export of georeferenced height/crown spread; if blocked, request research permission/extract rather than bypassing controls.
3. Inventory source rights, capture years, and on-campus coverage in `docs/references/ucla-source-manifest.json`.
4. Select 2–3 central-campus demo journeys for model evaluation and on-site verification.

## Original next steps (for hackathon)
1. Verify Mapbox credentials, mobile `npm install`, `expo install --fix` and actual native Android/iOS development build.
2. Download and inspect real UCLA graph; manually test campus route connectivity and pedestrian permissions.
3. Verify mobile-to-backend communication and render real route lines.
4. Find/validate independent building and tree heights; score short corridor with provenance and uncertainty.
5. Improve edge segmentation and constrained route candidate coverage; test hot/cold policies with actual known shade.
6. Test on campus with GPS and finish launch experience.
## Backend-only recent route history (2026-10-17)

- Added opt-in SQLite snapshots for the newest five distinct ordered campus POI pairs per private installation UUID. Repeated searches update recency; coordinate/GPS queries and failed route calculations are not saved. Database files remain gitignored.
- `POST /api/routes` retains its existing body and fresh calculation behavior; optional `X-Route-History-Key` enables saving. Two GET history endpoints return original request/conditions/results with an explicit historical flag, without invoking route or shade calculation. See contract v0.5 for future mobile integration.
- Verified **126 backend tests passed**, including six history cases covering persistence across connections, no recomputation, eviction/update, device isolation, coordinate exclusion, storage errors and concurrent writes. Used project-local temporary databases with unrestricted local test runner because restricted FastAPI tests stalled and the default system temporary directory denied access. Existing dependency deprecation warnings remain.
- `git diff --check` and skill mirror verification passed. Frontend history UI, live device integration and account authentication are **NOT implemented / NOT RUN**. Existing mobile behavior is unchanged by this slice.
