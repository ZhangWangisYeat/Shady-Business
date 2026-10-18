# Shady Business mobile ↔ FastAPI contract v0.4 (starter implemented)

Actual schema lives in `backend/app/api/schemas.py`; mirror DTOs in `mobile/src/api/types.ts`. GeoJSON is WGS84 `[longitude,latitude]`; distances meters, durations seconds, temperature Celsius, ISO 8601 offset-aware departure timestamps. The API is a **starter**; do not claim mobile integration is tested.

## `GET /api/health`
`{"status":"ok","dataset_status":"not_loaded|ready","shade_status":"unavailable|modeled"}`. The endpoint reports whether the OSM GraphML is actually on disk, never pretends a dataset is available.

## `GET /api/places?q=royce&limit=8`
Ranked campus search over `backend/app/places/ucla_places.json` (~400 named OSM features inside the UCLA campus boundary, ODbL). `q` max 100 chars; `limit` 1–20, default 8. Matches name prefix, then short/alt names (`bplate`), then every query word as a word prefix (`young research`), then address/category; buildings rank above streets and walkways with the same prefix.

Returns `{"places":[{"id":"royce-hall","name":"Royce Hall","coordinate":[-118.442189,34.072904],"category":"Building","address":null}],"attribution":"© OpenStreetMap contributors"}`. `address` is the OSM `addr:*` value when present, else `null`. **Coordinates are OSM building/area centers, not verified entrances**; the route snaps to the nearest walking-graph node, which may be on the far side of a large building. Clients must show `attribution` wherever results are listed.

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
    "segments":[{"shade_state":"unknown","duration_s":0,"sun_seconds":null,"unknown_seconds":0,"geometry":{"type":"LineString","coordinates":[]}}],
    "steps":[{"maneuver":"depart","instruction":"Head north on the walkway","way_name":null,"distance_m":0},
             {"maneuver":"arrive","instruction":"Arrive at your destination","way_name":null,"distance_m":0}]
  }]
}
```
Numbers and empty lines above are **schema placeholders only, NOT a real valid route**. Real responses always carry connected OSM graph geometries and nonzero durations/distances.

Enums: route `mode = fastest|recommended|maximum_shade`; step `maneuver = depart|straight|slight_left|slight_right|left|right|sharp_left|sharp_right|arrive`; `shade_state=shade|sun|unknown`; `optimization_quality=shortest_time|candidate_search|unavailable`; `same_as` refers to an earlier mode if exact path duplicates it. If any segment's exposure is unknown, `sun_seconds` for the route is **null** rather than falsely reporting a complete numeric exposure. `unknown_seconds` is measured walking time on unknown segments.

`steps` are built from the route's OSM edges (`backend/app/routing/directions.py`): a new step starts when the way name/type changes or the heading turns ≥35°, and steps under 15 m are folded into the previous one. `distance_m` is the distance walked after that maneuver until the next; the last step is always `arrive` with 0. `way_name` is the OSM name, or `null` for unnamed paths (the instruction then says "the walkway", "the stairs", etc.). Most campus footways are unnamed in OSM, so many steps read as a bare "Turn left".

When data is missing, all three route modes select the **same fastest graph path** with `same_as` set. Maximum shade uses candidate search, **not proven global optimum**. This will change when the optimizer is improved.

## Native UI
`plan (search → routes/directions) → navigate → arrived`, with error branch and explicit labeled demo mode. The start defaults to **Your location**: when a destination is chosen the app requests foreground permission, takes one GPS fix and sends `{"coordinate":[lon,lat]}` as the origin (no watcher until navigation). Fixes more than 1.5 km from campus center are rejected on the device with a message, because the walking graph doesn't reach them. Destinations, and optional other starts, are typed into a top search card backed by `/api/places`. A start other than your location is **preview only**: routes and directions are shown, but Start and Demo walk are hidden. Choosing both ends (or changing temperature) requests routes automatically. Foreground GPS permission only; no persisted tracks. Mapbox renders returned route features via `ShapeSource` and `LineLayer` without changing their coordinates (the draw-in animation only reveals a prefix of the returned geometry). Navigation shows the next step from `steps`.

## Errors
FastAPI HTTP `detail` includes `{code,message}` for known routing failures; Pydantic validation uses its standard HTTP 422 payload. Handle errors on mobile, don't silently replace with mock routes.
