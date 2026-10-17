# Shady Business — Native App Architecture + Algorithm Plan

## System boundary
`Expo SDK 57 / React Native / @rnmapbox/maps / foreground expo-location` ⇄ `FastAPI` ⇄ `[UCLA pedestrian graph, model-generated shade field, multiobjective route solver, weather adapter]`.

- **Mapbox is strictly the visual basemap and GPS/navigation camera surface**. Do not use its proprietary rendered 3D features/height data as inputs into your independent route engine absent applicable permission. Do not use Mapbox Directions or Navigation SDK for shade routes.
- Backend returns its **own GeoJSON** with graph paths and sun/shade/unknown segments. Mobile renders via Mapbox ShapeSource/LineLayer and follows position with native camera APIs.
- No persistent user account, trip logging, or production database needed. A versioned bounded test area supports fast local startup.

## Proposed module boundaries (scaffold later)
```
mobile/                         # Expo app: TypeScript + React Native
  app/                          # single App.tsx state machine (scaffold)
  src/components/               # search, route card, nav status, sheets
  src/map/                      # Mapbox adapter, overlays, camera
  src/location/                 # GPS permission, accuracy, simulator
  src/navigation/               # pure state machine, progress, turns
  src/api/                      # typed FastAPI transport
  __tests__/
backend/
  app/api/                     # Pydantic requests/responses
  app/places/                  # curated, sourced UCLA POIs
  app/routing/                 # graph loading/snap, candidate search
  app/shade/                   # raw geometry, shadow, sample, provenance
  app/weather/                 # temperature + fallback
  tests/
data/                           # license-vetted, bounded geodata
  README.md                    # never commit restricted data
```

## Shadow calculation: independent, no Google Solar runtime
**Stage 1, building shade:** acquire walkable OSMnx graph and vetted building polygons. Use tagged `height` where present, `building:levels` only as a clearly stated approximate-height estimator. Work in **projected meters** (e.g., EPSG:26911 near UCLA). For requested `America/Los_Angeles` timestamp, compute solar azimuth/elevation using Astral or pvlib. For obstruction height `h` and solar elevation `α > 0`, first-order level-ground shadow reach `L = h / tan(α)`, pointing opposite sun azimuth. Project / sweep each building footprint across a translated vector to make approximate shadow polygons; union / spatially index. Height uncertainty, uneven terrain and model limits must propagate into shade confidence.

**Stage 2, trees:** LA County LARIAC7 **TREE_CANOPY_2024** publishes a canopy classification drawn from 2023/2024 imagery and nDSM-derived processing. The classification does **not guarantee raw crown heights are exposed** through that service. Seek separately licensed underlying nDSM or field-measured height samples. Only with plausible heights/geometry project approximate crown shadow; use categorical tree opacity / seasonal assumptions rather than claiming photometric precision. If height not known, mark canopy prediction low-confidence or unknown, not certified shade.

**Stage 3, graph edge scoring:** densify each pedestrian edge geometry into points every ~2–5 m, project into shadow polygons at the **approximate time user traverses that point**, assign `sun`, `shade`, `unknown`. Estimate `sun_seconds = edge_duration × known_sun_fraction`; record `unknown_seconds`, known fraction and source vintage. For first milestone, static score at departure time with documented approximation; later step/time buckets (~5–15 min). Distinguish road centerline from correct sidewalk side; GPS ± several meters and canopy misregistration can flip state.

**Stage 4, route optimizer:** `Fastest` = shortest time with A*/Dijkstra. Current code enumerates up to 12 shortest-by-length paths; **this is not sufficient for global shade optimality**. Next implement edge-sun weighted and Pareto candidate search, dedupe, then validate each against the fastest duration and detour caps. Max Shade minimize sun seconds under cap; Recommended minimize `time + lambda(temperature) × sun_seconds` under tighter cap. When candidate enumeration is approximate, don't claim provable global optimum. Fallback to Fastest for unknown coverage / unusable weather; provide uncertainty, not fake values. Tests should verify monotonic shade preference on fixed graph, strict caps, tie behavior, duplicate routes and unknown data.

**Stage 5, mobile navigation:** GPS watcher foreground only; map-match nearest plausible location along route respecting reported accuracy, smoothing/hysteresis to prevent shade indicator flicker. Project current estimated position/time to shaded/unknown segments; show `Shade unknown` with poor GPS or incomplete model. Debounced off-route warning, simple maneuver cues, arrival when within destination radius **and** plausible progress. The demo simulator emits equivalent location samples and never passes as GPS.

## Data/provider plan
- Map visualization: Mapbox Standard style (standard, not satellite by default), via native RN wrapper. Public display token scoped; any native artifact download token kept in CI/developer secrets.
- Walking: OSMnx/OpenStreetMap, with footpath/steps/access restrictions reviewed for a small verified corridor; source attribution.
- Buildings: OSM tags first; explore vetted LA County/UCLA polygon/elevation sources. Heights frequently incomplete; approximate only with visible uncertainty.
- Canopy: LARIAC7 2024 as a **candidate**, must verify coverage, rights and meaningful heights separately. If not available, prioritize building-only correctly labeled modeled shade over fabricated tree shade.
- Weather: separate provider if terms permit; manual Celsius override + cold->fastest fallback if unavailable.
- **Google Solar API: EXCLUDED** from runtime. Google's Solar permitted uses are energy-focused and displayed results carry Google Maps map-display requirements.
- AI optional: only after core path works, an appropriately licensed vision model may segment vegetation where structured GIS data is missing; subject to uncertainty and deterministic validation. Do not introduce LLM into shortest-path core.

## Delivery and owners
- G0 **mobile shell**: Expo dev build, Mapbox map at UCLA on real phone, token and permission setup. Owner: mobile.
- G1 **routing**: verified OSM campus walking graph, static place index, Fastest JSON → real native polyline. Owners: backend + mobile.
- G2 **geometry**: one corridor modeled shadow with data date/limits; sampled segments and colored overlay. Owner: geospatial.
- G3 **optimizer**: three paths, temperature curve, summary metrics; API integration. Owner: routing.
- G4 **navigation**: start/preview, compass/pitch, live GPS + simulation, status, arrival. Owner: mobile.
- G5 **validation**: limited on-site observations, device and contract tests; polish only after correctness.

## Risks / mitigations
- **Native build setup**: Expo Go can't run rnmapbox; configure Expo development builds immediately; iOS local builds require Xcode/macOS.
- **React Native wrapper support**: community maintained. Pin tested versions and maintain fallback to MapLibre Native renderer if a blocking issue occurs.
- **Shade geometry incomplete**: choose bounded corridor, label modeled vs unknown, avoid claiming sun-safety; don't rely on proprietary 3D map meshes as data.
- **Different route data providers**: independently generated graph path may not coincide exactly with Mapbox 3D building visuals; show graph geometry and avoid cosmetic snapping that changes route.
- **GPS jitter**: use accuracy threshold, hysteresis and approximate sidewalk uncertainty.
- **Hot weather behavior**: validate UX heuristic with test cases; no medical claims.


## What is in the initial repository (October 17, 2026)
- `mobile/App.tsx`: native bottom-sheet-style interface with campus place chips, route comparison, temperature override, route preview, demo/GPS guidance, and arrival/reset. **Not device-tested.**
- `mobile/src/map/ShadyMap.tsx`: Mapbox Standard native view, routes colored by backend `shade_state` plus basic camera following. **Not device-tested.**
- `backend/app/main.py`: health / places / routes endpoints. `app/routing/graph.py`: live downloaded OSM graph loading, 12 shortest-by-length candidate search; API refuses to fake routes when missing.
- `backend/app/shade/model.py`: optional building-only planar geometric projected shadows from a license-vetted GeoJSON with `height_m`. This is **model source code only**: no valid UCLA file is bundled and real-world shade accuracy is not verified.
- `backend/app/routing/policy.py`: deterministic temperature-weighted candidate selection and detour caps. Offline tests run.
- **Important correctness guard:** no shade file -> unknown, not sunny; inability to show a shorter hot route is intentional until data is validated.

## Production hardening not done
Street-side-specific sidewalk geometry, best-path Pareto optimization, rich GPS map matching, turns, location smoothing, live ambient heat or remote weather provider, real campus dataset provenance validation, native build validation, tile/provider performance, accessibility audits and on-device reliability.
