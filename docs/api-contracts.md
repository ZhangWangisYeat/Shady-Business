# Shady Business mobile ↔ FastAPI contract v0.3 (starter implemented)

Actual schema lives in `backend/app/api/schemas.py`; mirror DTOs in `mobile/src/api/types.ts`. GeoJSON is WGS84 `[longitude,latitude]`; distances meters, durations seconds, temperature Celsius, ISO 8601 offset-aware departure timestamps. The API is a **starter**; do not claim mobile integration is tested.

## `GET /api/health`
`{"status":"ok","dataset_status":"not_loaded|ready","shade_status":"unavailable|modeled"}`. The endpoint reports whether the OSM GraphML is actually on disk, never pretends a dataset is available.

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
  "conditions":{"temperature_c":29,"temperature_source":"user","shade_model":"unavailable","data_as_of":null,"model_limitations":["No licensed usable shadow dataset loaded"]},
  "routes":[{
    "id":"fastest-01","mode":"fastest","same_as":null,
    "duration_s":0,"distance_m":0,"sun_seconds":null,"unknown_seconds":0,
    "optimization_quality":"shortest_time",
    "geometry":{"type":"LineString","coordinates":[]},
    "segments":[{"shade_state":"unknown","duration_s":0,"sun_seconds":null,"unknown_seconds":0,"geometry":{"type":"LineString","coordinates":[]}}]
  }]
}
```
Numbers and empty lines above are **schema placeholders only, NOT a real valid route**. Real responses always carry connected OSM graph geometries and nonzero durations/distances.

Enums: route `mode = fastest|recommended|maximum_shade`; `shade_state=shade|sun|unknown`; `optimization_quality=shortest_time|candidate_search|unavailable`; `same_as` refers to an earlier mode if exact path duplicates it. If any segment's exposure is unknown, `sun_seconds` for the route is **null** rather than falsely reporting a complete numeric exposure. `unknown_seconds` is measured walking time on unknown segments.

When data is missing, all three route modes select the **same fastest graph path** with `same_as` set. Maximum shade uses candidate search, **not proven global optimum**. This will change when the optimizer is improved.

## Native UI
`search → compare → navigate → arrived`, with error branch and explicit labeled demo mode. Foreground GPS permission only; no persisted tracks. Mapbox renders returned route features via `ShapeSource` and `LineLayer` without changing their coordinates. The current routing algorithm does not yet output turn-by-turn instructions.

## Errors
FastAPI HTTP `detail` includes `{code,message}` for known routing failures; Pydantic validation uses its standard HTTP 422 payload. Handle errors on mobile, don't silently replace with mock routes.
