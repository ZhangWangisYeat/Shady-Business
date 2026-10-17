# UCLA tree crown integration — 2026-10-17

## Implemented local behavior

The existing CSV from the chat **查找 UCLA 植被数据** is the source:
`arborpro-inspect/ucla_tree_inventory.csv` in the parent workspace. It contains
20,177 records from the UCLA public ArborPro inventory. This feature reads that
existing local file only; it does not repeat the other chat's download or use a
live provider at request time. The user explicitly requested local integration.
Public redistribution rights have not been established; raw/normalized geodata
is kept in ignored local storage and is not staged or uploaded.

The study rectangle matches the existing OSM building extraction:
`west=-118.448, south=34.0675, east=-118.438, north=34.0755`. This is a bounded
central-campus study area, NOT a verified campus property boundary or complete
campus coverage. Nearby outside trees/buildings may cast shadows into it.

Actual import report:

| Count | Records |
| --- | ---: |
| Source CSV | 20,177 |
| Outside study rectangle | 16,553 |
| Non-tree records inside rectangle | 1 |
| Standing-tree records retained | 3,623 |
| Retained records with usable height AND crown spread | 3,623 |
| Invalid coordinates | 0 |

Status `1` corresponds to Tree in the public viewer (cross-checked using visible
inventory records). Other codes are excluded. Status Tree does not prove that a
tree is currently alive or fully foliated; current condition is unavailable.
Missing/zero/nonfinite heights or spread in standing-tree inputs remain null
and unmodeled, never replaced by default heights or a fixed 4 m radius.

## Reproduce the intake

With existing backend dependencies available, from the clone root:

```powershell
python scripts/import_arborpro_trees.py --csv ../arborpro-inspect/ucla_tree_inventory.csv --bbox -118.448 34.0675 -118.438 34.0755 --out backend/data/ucla_trees.geojson
```

The importer preserves IDs/species, converts height feet × 0.3048 and crown
spread feet × 0.3048 / 2 to radius meters, and records CSV SHA-256, source URL,
original units, filter rectangle and import counts. Import time is NOT used as
survey time. Individual observation dates are unavailable; `data_as_of=null`.

The [UCLA plan, PDF page 18](https://sustain.ucla.edu/wp-content/uploads/2025/07/Reduced-Size-Final-UCLA-Urban-Forest-Management-Plan-July-2025.pdf#page=18)
defines spread as horizontal crown extent. DBH is not used as crown diameter.

`load_model()` automatically combines the existing buildings with normalized
trees at `backend/data/ucla_trees.geojson`, or override `SHADY_TREE_FILE`.
Restart a running server after changing local files because model loading is
cached. Missing tree files preserve building-only operation; tree-only inputs
also work. Malformed CRS/units/duplicate identities are rejected.

## Crown mathematics and assumptions

Input total height `h` is the top of a tree, and `r` is horizontal crown radius.
If measured crown base `b` is available, vertical semi-axis `rz=(h-b)/2`.
Otherwise assume `rz=min(r,h/2)` (a round crown compressed to stay above ground)
and explicitly report that this vertical shape is assumed. Center elevation
`zc=h-rz`. No unobserved crown-base value is stored as a measurement.

For solar elevation `alpha > 2°`, parallel ground projection of this ellipsoid
is an ellipse with:

- Major semi-axis: `sqrt(r² + (rz / tan(alpha))²)` along the shadow heading.
- Minor semi-axis: `r`, perpendicular to the shadow heading.
- Center displacement: `zc / tan(alpha)`, opposite solar azimuth.

The implementation polygonizes the ellipse with 128 segments. At zenith it
reduces to the horizontal crown footprint. It does NOT sweep a floating crown
all the way down to its trunk, which would create false shaded corridors.
It assumes opaque leaves, flat ground and approximate local projected north;
foliage transmission, current condition, vertical crown shape, terrain and exact
sidewalk position remain uncertain. Low solar angles `(0,2]` return unknown;
night is zero direct sunlight with separate internal `no_direct_sun` state.

Union building and tree polygons before intersecting roads, so overlaps count
once. Exact road split points preserve source traversal order. Uncovered pieces
remain unknown unless obstruction coverage is explicitly verified; loading a
tree inventory never establishes completeness by itself.

## API and command integration

`/api/routes` now consumes precise per-edge scoring and returns actual ordered
shade/sun/unknown pieces instead of threshold-labeling entire mixed edges. The
public JSON and mobile enums remain unchanged. At night the public overlay is
`unknown` because shade/sun classification is inapplicable, while exposure is
known to be zero (`sun_seconds=0`, `unknown_seconds=0`) and conditions explain it.
Incomplete daylight exposure yields route `sun_seconds=null`, preserving the
existing conservative fastest-route fallback. Temperature policy is unchanged.

```powershell
python scripts/score_route_shade.py --route local-data/route.geojson --buildings backend/data/ucla_buildings.geojson --trees backend/data/ucla_trees.geojson --departure "2026-10-17T15:00:00-07:00"
```

## Verified results

- **96 backend tests passed**, including 32 tree-specific cases: numeric unit
  conversion, exclusion/unknown records, source provenance, directions, solar
  boundaries, 3D surface projection cross-check, crown base, source union,
  standalone CLI and unchanged HTTP schema/daylight/night behavior.
- Real local data: **134 OSM-tagged building heights + 3,623 tree crowns** loaded.
  Their combined afternoon planar shadow union was generated successfully.
- Offline real-data API check used the existing **1,086-node / 2,646-edge** OSM
  graph in memory for Royce Hall → Ackerman, not a fabricated campus route.
  This does not install a default GraphML or start a persistent server.

For the same 370.04 m / 284.65 s fastest path on 2026-10-17:

| Departure (Los Angeles) | Building-only modeled shade (s) | Building + tree modeled shade (s) | Unknown (s) | API elapsed (s) |
| --- | ---: | ---: | ---: | ---: |
| 09:00 | 168.897 | 214.263 | 70.387 | 1.206 |
| 12:00 | 154.262 | 205.425 | 79.225 | 1.300 |
| 15:00 | 109.490 | 180.560 | 104.090 | 1.178 |

Returned routes contained 34/42/36 pieces respectively; route/segment duration
and unknown totals and adjacent geometry joins were checked. Nighttime API
behavior passed. The local detailed result is
`backend/data/canopy_validation.json` (ignored by Git).

These are model/pipeline comparisons, NOT measured shade accuracy, full campus
coverage, device validation or proof that a route is safe/cool. Incomplete
coverage still produces coincident route choices. The installed local Shapely
emits deprecation warnings from existing `shapely.ops.transform` calls; these are
not test failures. Physical-device/field validation is NOT RUN for this slice.
