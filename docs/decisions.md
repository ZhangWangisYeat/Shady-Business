# Architecture decision log

## ADR-001 — Native mobile over browser app
Expo + React Native with Mapbox Maps SDK and community RN wrapper. A foreground walking app is the product; desktop web is not the target. Native modules require a development build. No app-store release required for hackathon testing.

## ADR-002 — Separate map display from route solving
Use native Mapbox for basemap/UI only. FastAPI owns verified walkable OSM graph, geometric model, temperature logic, and custom GeoJSON route output. This preserves independence and avoids treating map rendering as geospatial evidence.

## ADR-003 — Exclude Google Solar from runtime
Google Solar Data Layers use is restricted by its standard energy-related permitted-use terms; do not query or display its data in the prototype. Build an independent shade model with cleared geometry and provenance.

## ADR-004 — Unknown means unknown
Without vetted shade inputs, all edges are unknown; three route modes legitimately coincide. Don't label paths shaded based on intuition, historical screenshots or unmapped tree canopies. Never invent route diversity.

## ADR-005 — Use stable Expo 57 baseline
SDK 57 is stable with RN 0.86 as of repo drafting; SDK 58 was freshly released on October 15, 2026. Pin resolved dependencies after a successful mobile build and upgrade deliberately, not mid-hackathon.

## ADR-006 — Source and implementation status
Graph download is opt-in and not included in ZIP; offline tests use synthetic graphs only. The current k-shortest candidate enumeration is a bootstrap algorithm to replace/extend with Pareto or multiweighted search once shade coverage is validated.

## ADR-007 — UCLA-specific source-first shade modeling
2025 UCLA Urban Forest Management Plan reports field tree-height and crown-spread measurements, with a public ArborPro inventory viewer. Source catalog and machine-readable manifest are added. Do not claim CSV export or downstream rights are available until verified. Use licensed tree inventory + OSM campus footpaths/buildings; use 2024 county canopy only after permissions review and USGS 3DEP if campus lidar coverage is confirmed. Limit first shadow computation to selected UCLA paths rather than all LA.

## ADR-008 — Template freeze ahead of hackathon
Retain existing Expo + Mapbox and FastAPI starter files today. Conduct data audit, normalizer, source tracking and geometric algorithm planning now; implement/validate route and shade improvements after the hackathon begins. No new infrastructure or unnecessary UI/backend code paths as part of this patch.

## ADR-009 — Campus place search from OpenStreetMap (2026-10-17)
Typed start/destination search uses named OSM features inside the UCLA campus boundary, fetched once by `scripts/fetch_ucla_places.py --confirm-network` (free Overpass) and committed as `backend/app/places/ucla_places.json` with ODbL attribution shown in the app. Google Places/Apple Maps data is excluded: their terms forbid caching or reuse outside their own maps and they are paid. Mapbox Search is excluded for now (billable beyond its free tier; no spend without approval). UCLA's own campus map has no stated reuse license, so it is not scraped. Approved by the user as an exception to the ADR-008 template freeze. Known gap: pins are building centers, not entrances.
