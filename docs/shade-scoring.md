# Route shade scoring: local algorithm slice

This module scores supplied routes; it does not search for routes or change the
temperature policy. No paid API, credentials, downloaded geodata, or mobile schema
changes are needed. Synthetic tests demonstrate geometry correctness, not field
accuracy. This is a building-plus-tree static departure-time estimate. The actual
local ArborPro CSV is now connected; see `docs/tree-shade-integration.md`.

## Python integration

Run with the existing backend dependencies installed (`pip install -e "backend[dev]"`
from the repository root). The Python import root is `backend/`.

```python
from datetime import datetime
from pathlib import Path
from app.shade.model import read_model, with_tree_file, build_shadow_field
from app.shade.scoring import RouteEdge, score_route

model = read_model(Path("backend/data/ucla_buildings.geojson"))
model = with_tree_file(model, Path("backend/data/ucla_trees.geojson"))
field = build_shadow_field(model, datetime.fromisoformat("2026-10-17T15:00:00-07:00"))
# Obtain these ordered coordinates and durations from the routing provider.
edges = [RouteEdge(tuple(edge_coordinates), edge_duration_s)]
score = score_route(edges, field)
payload = score.to_dict()
```

`RouteEdge` needs WGS84 `[longitude, latitude]` coordinates and a finite positive
duration in seconds. Edges must be nonzero length, within the current UCLA service
bounds, ordered and connected (10 micrometer projection tolerance). Direction,
polyline vertices and repeated traversals are preserved. Edge time is distributed
in proportion to metric distance within that edge; use multiple edges for
different walking speeds. Output is not rounded, so the caller can format it
without accumulating rounding errors.

The existing HTTP API now uses precise `score_route` segments with the same
public JSON shape. Its v0.3 nighttime overlay remains `unknown` (daytime shade
is inapplicable), with zero direct-sun/unknown exposure seconds and an explanatory
condition. The standalone scorer retains its separate `no_direct_sun` state.
Existing `load_model`,
`shadow_polygons` and `fraction_sun` imports remain available. The legacy
`fraction_sun` now uses exact intersections rather than nine sample points, but
its complement alone does not establish verified sunshine. New consumers must
use `score_route` for coverage-aware results.

## Geometry and score

1. Project inputs to EPSG:26911 in meters, with `[longitude, latitude]` axis order.
2. Astral computes geometric solar elevation `alpha` and azimuth `A` at the UCLA
   reference point. Offset-aware timestamps are mandatory; UTC and equivalent
   local/DST timestamps give the same solar position.
3. For each known building height `h`, compute `L = h / tan(alpha)` and displacement
   `(-L sin(A), -L cos(A))`. Sweep the footprint along that vector by unioning the
   original, translated footprint and swept ring edges. This retains concavities,
   courtyard openings and disjoint MultiPolygon components instead of filling
   their convex hull. Azimuth is used as local projected north; grid convergence
   and intra-campus solar-angle variation are small unmodeled approximations.
4. Project normalized tree crowns as opaque ellipsoids using total height and
   half the horizontal spread. See the crown formula and explicit vertical-shape
   assumption in `tree-shade-integration.md`. Union overlapping building/tree
   shadows, then split each original straight road piece at
   shadow and verified-coverage boundaries. Classify each resulting interior.
   This includes narrow shadows, collinear overlaps, and zero-length tangencies.
5. For each piece, `duration = edge_duration * piece_length / edge_length`.
   Sum duration by state. Repeated traversals count again; overlapping shadows
   count once. No LLM or temperature enters this calculation.

States:

| State | Meaning |
| --- | --- |
| `shade` | Covered by a modeled building shadow; still an estimate |
| `sun` | Outside all modeled shadows AND inside verified obstruction coverage |
| `unknown` | Missing coverage/data, or solar elevation in `(0, 2]` degrees |
| `no_direct_sun` | Sun at/below horizon; distinct from daytime shade |

Low-angle shadows are not silently truncated to 250 m. At elevation above 2 degrees,
full planar reach is retained; low-angle/boundary predictions particularly depend
on sufficiently buffered obstacle data. At night, building data is unnecessary to
establish no direct sunlight. No claim of thermal comfort follows from any state.

Important outputs:

| Field | Definition |
| --- | --- |
| `shade_seconds` | Modeled walking seconds in building shade |
| `known_sun_seconds` | Walking seconds modeled in direct sun |
| `unknown_seconds` | Walking seconds with unknown exposure |
| `sun_seconds` | Complete modeled sun total; `null` if ANY exposure unknown |
| `sun_seconds_min/max` | Known sun / known sun + unknown; bounds conditional on the model, not statistical confidence |
| `shade_fraction` | Shaded distance / route distance, only for complete daylight coverage; otherwise `null` |
| `known_fraction` | Fraction of walking TIME with a modeled state, including nighttime |
| `segments` | Ordered WGS84 GeoJSON LineStrings, states, distances, durations and exposure |
| `source`, `data_as_of`, `limitations` | Passed-through provenance and explicit model limits |

Example: a synthetic 100-second route with 40 seconds in shade, 30 in verified sun
and 30 unknown returns `sun_seconds=null`, bounds `[30, 60]`, and
`known_fraction=0.7`. Unknown is never treated as shade or zero sunlight. Candidate
selection must not rank an incomplete route as having less sun just because its
known sun total is smaller.

## Building and coverage input

Use only license-cleared GeoJSON `FeatureCollection`, containing valid WGS84
Polygon/MultiPolygon footprints and numeric `properties.height_m` in `[1, 250]`.
Invalid geometry/CRS is rejected. Missing/invalid heights are not invented: these
features remain unmodeled and disable verified sunshine claims for the file.

Optional top-level `metadata`:

```json
{
  "source": "Actual authorized source name",
  "data_as_of": "Actual source survey date, if known",
  "coverage_complete_verified": false,
  "coverage_geometry": null
}
```

To permit `sun`, both the flag must be true and `coverage_geometry` must be an
explicit WGS84 Polygon/MultiPolygon whose obstruction completeness has been
verified. A global boolean or building bounding box is insufficient. Verification
must include trees, missing-height buildings and obstacles outside the corridor
that could cast shade into it. Setting the flag does not itself validate this.
Building footprints are included in obstructed regions; route owners must ensure
their pedestrian graph does not traverse building interiors. Raw local building
and tree assets remain ignored by Git; no verified complete coverage is claimed.

## Local command

Route input is one GeoJSON `Feature` or a `FeatureCollection` of connected,
ordered `LineString` features, each with `properties.duration_s`.

```powershell
python scripts/score_route_shade.py --route local-data/route.geojson --buildings backend/data/ucla_buildings.geojson --departure "2026-10-17T15:00:00-07:00"
```

Add `--trees backend/data/ucla_trees.geojson` to include measured crown dimensions.
Either source can be supplied independently. Omit both to check explicit
unavailable/nighttime behavior. Add
`--out local-data/score.json` to save a result; otherwise JSON goes only to stdout.
Do not commit personal route inputs/outputs. The command makes no network calls.

## Verification

```powershell
cd backend
python -m pytest tests/test_shade.py -q
```

Tests cover projection/reach, concavity/courtyards/MultiPolygon, overlap, narrow
shade strips, tangency, partial coverage, duration/distance conservation, route
reversal/retracing, unequal walking speeds, invalid inputs, missing heights,
timezone/DST equivalence, solar-angle boundaries and the local command pipeline.
Real corridor validation and mobile integration are separate milestones.
