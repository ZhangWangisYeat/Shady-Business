# Shady Business mobile ↔ FastAPI contract v0.4

Actual schema lives in `backend/app/api/schemas.py`; mirror DTOs in `mobile/src/api/types.ts`. GeoJSON is WGS84 `[longitude,latitude]`; distances meters, durations seconds, temperature Celsius, ISO 8601 offset-aware departure timestamps. Backend contract tests are implemented; physical-device integration remains a separate gate.

## `GET /api/health`
`{"status":"ok","dataset_status":"not_loaded|ready","shade_status":"unavailable|modeled","shade_coverage":"unavailable|unverified|verified"}`. The endpoint reports whether the OSM GraphML and shade inputs are actually loaded and never equates a modeled dataset with verified coverage.

## `GET /api/places?q=royce`
Returns `{"places":[{"id":"royce-hall","name":"Royce Hall","coordinate":[-118.4422,34.0728]}]}`. **Coordinates are approximate starter estimates requiring verification.**

## `POST /api/routes`
Request:
```json
{"origin":{"place_id":"royce-hall"},"destination":{"place_id":"ackerman-union"},"departure_time":"2026-10-17T15:00:00-07:00","temperature_c":29}
```
Or use `{"coordinate":[longitude,latitude]}` for a permissioned origin. Requires downloadable graph; if missing, returns HTTP 503 with FastAPI detail envelope.

Response shape (no synthetic numerical assertions):
```json
{
  "conditions":{"temperature_c":29,"temperature_source":"user","shade_model":"unavailable","shade_coverage":"unavailable","solar_status":"daylight","data_as_of":null,"model_limitations":["No licensed usable shadow dataset loaded"]},
  "routes":[{
    "id":"fastest-01","mode":"fastest","same_as":null,
    "duration_s":0,"distance_m":0,"sun_seconds":null,"unknown_seconds":0,"coverage_fraction":0,
    "optimization_quality":"shortest_time",
    "geometry":{"type":"LineString","coordinates":[]},
    "segments":[{"shade_state":"unknown","duration_s":0,"sun_seconds":null,"unknown_seconds":0,"geometry":{"type":"LineString","coordinates":[]}}]
  }]
}
```
Numbers and empty lines above are **schema placeholders only, NOT a real valid route**. Real responses always carry connected OSM graph geometries and nonzero durations/distances.

Enums: route `mode = fastest|recommended|maximum_shade`; `shade_state=shade|sun|unknown`; `optimization_quality=shortest_time|candidate_search|unavailable`; `same_as` refers to an earlier mode if exact path duplicates it. `solar_status=daylight|night|low_sun|unavailable` describes whether daytime classification applies. `shade_coverage` distinguishes no model, modeled-but-unverified data and independently verified model coverage. If any segment's exposure is unknown, `sun_seconds` for the route is **null** rather than falsely reporting a complete numeric exposure. `unknown_seconds` is measured walking time on unknown segments; `coverage_fraction = 1 - unknown_seconds / duration_s`, clamped to `[0,1]` and calculated from the returned rounded seconds.

Local tree-integration slice: the backend now splits original edges at modeled
building/tree shadow and coverage boundaries, so mixed edges can return multiple
ordered segment geometries without adding fields or enums. Missing tree
dimensions remain unmodeled; data acquisition does not establish full coverage.
At night, `shade_state=unknown` means daytime shade classification is inapplicable,
while direct-sun exposure is known zero: segment/route `sun_seconds=0` and
`unknown_seconds=0`, with explanatory `conditions.model_limitations`. The internal
standalone scorer uses a distinct `no_direct_sun` state; it is not a mobile enum.

When the Fastest path has unknown exposure, all three route modes select the **same fastest graph path** with `same_as` set. When Fastest is completely scored, routing explores the bounded subgraph of completely scored edges, excludes unknown edges, deduplicates time- and shade-weighted paths, then applies the documented detour policies. Maximum shade remains a `candidate_search`, **not a proven global optimum**.

## Native UI
`search → compare → navigate → arrived`, with error branch and explicit labeled demo mode. Foreground GPS permission only; no persisted tracks. Mapbox renders returned route features via `ShapeSource` and `LineLayer` without changing their coordinates. The current routing algorithm does not yet output turn-by-turn instructions.

## Errors
Expected API and validation failures use one envelope:

```json
{"detail":{"code":"SAME_ENDPOINT","message":"Start and destination are too close. Choose another destination.","retryable":false,"field":"destination"}}
```

`field` is optional. `retryable=true` is reserved for temporary failures. Current
codes are `PLACE_NOT_FOUND` (404), `INVALID_REQUEST`, `OUTSIDE_SERVICE_AREA`,
`INVALID_TEMPERATURE`, `INVALID_DEPARTURE_TIME`, `SAME_ENDPOINT`, `SNAP_TOO_FAR`,
`NO_WALKABLE_PATH` (422), and `GRAPH_NOT_READY` (503). A graph 503 includes a
short `Retry-After` header. Mobile preserves the selected query, presents an
appropriate retry/change-location action, uses a 5-second places timeout and a
20-second routes timeout, and ignores route responses made stale by input edits.

Missing shade inputs already produce a successful route response with unknown
exposure. A known malformed/unreadable local shade dataset now follows the same
safe fallback: return the real graph Fastest path for all three modes, set
`shade_model`/`shade_coverage` to `unavailable`, keep `sun_seconds=null`, and add
the limitation. It never substitutes a mock route. Unexpected programming errors
remain server errors rather than being mislabeled as user input failures.
