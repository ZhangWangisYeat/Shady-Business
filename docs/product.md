# Shady Business — Native Mobile Product Specification v0.2

## Target
People walking 0.2–2 km across UCLA; iOS/Android handheld experience. Desktop is for developer tooling and optional simulator, **not** the product. The UI should feel familiar to mapping users, without copying proprietary brand assets.

## Required user journey
1. **Search:** full-screen interactive UCLA map; two searchable campus POIs with suggestions; start may use GPS (permissioned), manual POI or map tap. Prevent same-point/unconnected/outside-data routes gracefully.
2. **Compare:** a native bottom sheet with Fastest / Recommended / Maximum Shade; each displays time, distance, **modeled direct-sun minutes**, data coverage. All route lines follow real graph geometries. Mark segments **shade / sun / unknown** in distinguishable colors with legend; allow departure-time choice and temperature shown with source.
3. **Select:** tap a choice to preview its line and details; press **Start** to enter navigation; Back returns to the same query.
4. **Navigate:** foreground GPS foreground-only permission; native map location puck, pitch, user-bearing (with camera smoothing), progress and basic next-turn cues calculated from path shape; persistent prominent **In shade / In sun / Shade unknown** indicator driven by path projection, time and accuracy. Off-route/poor GPS => tell user; do not assert shade. Deterministic **Demo walk** traverses the same state machine for hackathon demonstrations.
5. **Arrive:** proximity + credible route-progress check / completion of simulation, then **Arrived** and **Plan another route** back to Search. Stop location subscription.

Navigation is a tilted forward-following vector map, **not** photorealistic Street View or AR. Background navigation, lock-screen directions, voice, accounts and app-store publication are post-MVP.

## Route rules
- **Fastest:** least travel seconds on connected pedestrian graph.
- **Maximum Shade:** least estimated *direct-sun seconds* among explored walkable paths satisfying `duration <= min(1.6 × fastest duration, fastest duration + 12 minutes)`; optimize sunlight exposure rather than percent shade. If algorithm only enumerates candidates, label 'least sunlight found' rather than mathematically exact global optimum.
- **Recommended:** at or below **65°F / 18.3°C**, exactly Fastest; between 65°F and **90°F / 32.2°C**, increase the willingness to trade seconds for less direct sun; above 90°F clamp to configured hottest mode. Use `J = travel_seconds + lambda(temp) × direct_sun_seconds` with `lambda` rising smoothly from 0 to a calibrated upper coefficient, while bounding travel time by `fastest × (1 + detour_fraction(temp))` (0–35%). A hard detour bound alone does not make a balanced recommendation; use the joint score and test monotonic preference on fixed fixtures. These are design heuristics, **not clinical thresholds**.
- If two modes select the same path, show that truthfully. No fake route choices. If shade data unreliable, mark uncertainty and degrade gracefully to Fastest rather than implying guaranteed coolness.

## UI states
`search -> fetching -> comparing -> preview -> navigating -> arrived -> search`; branches `gps_denied`, `off_route`, `no_route`, `shade_unknown`, `provider_error`. Show route-source and temperature-source metadata where useful; keep core cards uncluttered. Native screen safe areas, gestures and bottom sheet must not occlude the map position/directions.

## Acceptance gates
- G0 phone build opens Mapbox Standard and responds to touch, with accessible map attribution.
- G1 choosing two real campus points yields a visibly connected graph-based Fastest path.
- G2 real geodata-derived modeled sun/shade/unknown can be inspected on a selected, verifiable 300–500m UCLA corridor with metadata/vintage; no disguised simulation data.
- G3 all three policies return bounded routes with coherent duration/distance/exposure; cold Recommended == Fastest.
- G4 Start -> live GPS and deterministic Demo walk -> changing status -> Arrived -> reset work on an actual phone. Simulated status clearly labeled.
- G5 tests and small field validation for the selected corridor. Explicitly distinguish **modeled direct sun** from heat safety, weather or actual temperature.

## Not in MVP
Citywide coverage; paid AI voice; photorealistic Street View; health-risk predictions; real-time tree changes/cloud shadow forecasts; true accessibility guarantees; persistent trip records; background/locked-phone guidance.
