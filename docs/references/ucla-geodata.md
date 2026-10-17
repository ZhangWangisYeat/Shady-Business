# UCLA Shade Geometry & Licensing — research leads (2026-10-17)

## Confirmed source descriptions; UCLA applicability still to verify
- LA County LARIAC7 `TREE_CANOPY_2024` ImageServer: https://image.gis.lacounty.gov/image/rest/services/LARIAC7/TREE_CANOPY_2024/ImageServer . Public description states it combines NDVI from 2024 imagery with height-derived nDSM products; underlying capture includes **2023/2024**. This is a **tree classification**, not necessarily accessible per-tree heights or exact current shadow data.
- LARIAC7 folder: https://image.gis.lacounty.gov/image/rest/services/LARIAC7 . Listing shows canopy 2023/2024 and 2023 land cover, **not a confirmed public raw nDSM service**.
- LA County GIS: https://planning.lacounty.gov/maps-and-gis/gis-data/ . Verify data reuse/redistribution terms before storing raster extracts in Git or publishing app.
- OpenStreetMap building `height` and `building:levels` tags: https://wiki.openstreetmap.org/wiki/Key:building:levels . `building:levels` is not a measured height; estimating meters/level introduces uncertainty.
- UCLA campus map download: https://map.ucla.edu/downloads/ . Good cross-check for footpath network, not automatically a routable 3D source.

## What Mapbox does NOT solve
Mapbox Standard shows plausible 3D buildings, tree models and visually attractive lighting; this **does not authorize reusing Mapbox's underlying 3D map data as an independent routing-height dataset**, and its visual shadows are **not** a reliable pedestrian sun/shade API. Keep model and display datasets separate.

## Feasibility experiment
1. Choose a short UCLA route corridor and verify OSM walking paths against official campus maps or on-site observations.
2. Identify which building polygon geometries have actual `height`; label estimates from `building:levels` and unknown polygons.
3. Verify LARIAC7 tile export, UCLA footprint and reuse license; find **independently licensed actual height** (nDSM, LiDAR or limited measured estimates) before time-dependent tree shadows.
4. Compute approximate building shadows for 9 AM / noon / 4 PM on one date; compare spatial position with actual on-site observation where practical. Record model date/provenance, false certainty, and road-centerline/sidewalk mismatch.
5. Keep no-data sections `unknown`. Never assert model predicts heatstroke risk, temperatures, live cloud shadows or exact skin-level radiation exposure.
