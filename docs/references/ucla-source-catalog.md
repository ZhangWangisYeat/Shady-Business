# UCLA-first geospatial source catalog — Shady Business

**Researched:** 2026-10-17. **Scope:** UCLA main campus, not Los Angeles citywide. Source discoverability is not proof that downloadable files have been acquired or reuse licensed. `source-manifest.json` is the machine-readable companion. Do not commit third-party source imagery or restricted LARIAC datasets without verifying rights.

## Tier 1 — specific campus data to inspect first

### UCLA public tree inventory (2023–24 observations; 2025 plan)
- **Official introduction:** https://sustain.ucla.edu/landscape-and-biodiversity/
- **Public tree viewer:** https://app.arborprousa.com/viewer/7q07Ea8G2uVSf6KR/legacy_tree/ku2laqgzx6
- **2025 management plan (PDF):** https://sustain.ucla.edu/wp-content/uploads/2025/07/Reduced-Size-Final-UCLA-Urban-Forest-Management-Plan-July-2025.pdf
- **Verified:** The plan documents an inventory performed in 2023–2024 and published in 2025; records include location, height (feet), crown spread (feet), DBH, live crown ratio, species and condition. It reports **12,423 campus tree sites** and **almost 29% campus canopy** (not all inventory sites necessarily represent live trees).
- **Still to verify:** whether the *public* ArborPro viewer allows CSV export; exactly which coordinates and measurements are exposed; whether UCLA/ArborPro authorizes bulk export, model reuse and GitHub redistribution.
- **Next move:** Open viewer in a browser → select a small central-campus set → look for ArborPro's `Reporting > Export CSV` or `Open Inventory View > Report` controls (see https://arborprousa.com/faq/). If public export is unavailable, request a small explicitly licensed research extract from UCLA Sustainability/Facilities. Do not bypass viewer access controls.
- **Mapping contribution if permission granted:** actual stem/tree points plus measured height and crown spread, useful to approximate time-dependent crown shadows. Record unit conversions and source vintage. Tree crowns are not perfectly spherical or opaque.

### Official UCLA campus/accessibility map
- **Source:** https://map.ucla.edu/downloads/
- **Example 2025 printable campus map:** https://map.ucla.edu/downloads/pdf/UCLA_Campus_BW_Map.pdf
- **Verified:** UCLA Facilities Management publishes a campus map and accessibility map with routes/entrances. Contact for custom geospatial formats: `spaceinv@facnet.ucla.edu` as stated on that official page.
- **Use:** visually validate important passages, steps, construction closures, ramps, building/POI locations, and route directions. **Do not** treat a PDF image as a GPS-accurate routing graph without georeferencing.

## Tier 2 — geospatial coverages

### LA County LARIAC7 2024 tree-canopy ImageServer
- **Endpoint:** https://image.gis.lacounty.gov/image/rest/services/LARIAC7/TREE_CANOPY_2024/ImageServer
- **Verified:** countywide raster, ~1 m cells, combining 2024 infrared vegetation imagery and 2023/2024 height-related measurements; service describes heights above about 10 feet in its classification. Public ArcGIS ImageServer advertises export and analysis capabilities.
- **Crucial limitation:** This **binary canopy classification does not expose each crown's height**, despite having used height data during processing. Its reuse/redistribution license is **not confirmed** by mere public visibility. It may be useful to refine tree-crown extents and find omitted trees *once rights are cleared*.
- **Do not:** treat canopy presence as exact shaded-ground geometry at a chosen hour, or copy LARIAC imagery/rasters into public GitHub without a clearance.

### LA County 2023 building outlines with HEIGHT/ELEV
- **Endpoint:** https://rpgis.isd.lacounty.gov/arcgis/rest/services/GISNET_Public/MapServer/434
- **Metadata:** https://public.gis.lacounty.gov/arcgis/rest/services/DRP/GISNET_Public/MapServer/434/iteminfo
- **Verified:** public viewer shows polygons with `HEIGHT` and `ELEV` metadata; some footprint source imagery captured Jan–Jun 2023.
- **Critical licensing result:** metadata's `licenseInfo` says **"LARIAC Members only"**; credits include EagleView/Pictometry. Public query access is **not** permission to copy or redistribute. Treat this as a geometry/quality reference pending explicit reuse permission, not a default input for a public app.

### OpenStreetMap pedestrian and building features
- **Source/license:** https://www.openstreetmap.org/copyright and https://osmfoundation.org/wiki/Licence_and_Legal_FAQ
- **Graph loader already in repo:** `scripts/fetch_ucla_graph.py` (user-run; network required).
- **Use:** paths/sidewalks/building outlines, some buildings with `height` or `building:levels`. ODbL obligations, attribution and derivative-database conditions apply. `building:levels` is only a **rough height estimate**; retain uncertainty and distinguish inferred from measured heights.
- **First-day check:** walk from Royce Hall to Ackerman Union; inspect pedestrian connectivity against UCLA accessibility map. Paths through buildings/locked gates and steps need handling.

### USGS 3DEP Lidar Explorer / lidar point cloud
- **Browse/query:** https://www.usgs.gov/tools/lidarexplorer
- **Overview and rights:** https://www.usgs.gov/3d-elevation-program/about-3dep-products-services
- **Verified:** USGS offers public-domain lidar point clouds and digital elevation models, free of charge and without use restrictions. Check the latest **UCLA-specific** coverage year, resolution and processing sizes; site availability **has not been verified** for this exact campus footprint.
- **Important:** bare-earth DEM alone gives topography, **not** building/tree heights; point clouds with surface returns can potentially provide DSM – DTM height differences. Processing lidar should be a stretch task, not a prerequisite for Saturday's template.

## Images for visual checking, NOT a substitute for geodata
- **Wikimedia Commons UCLA campus:** https://commons.wikimedia.org/wiki/Category:Campus_of_the_University_of_California,_Los_Angeles . Inspect each file's license and image date (example CC-BY-SA 4.0: https://commons.wikimedia.org/wiki/File:2019_UCLA_Royce_Hall_1.jpg ).
- **Mapillary:** https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data . Community street-level imagery can help validate visible obstructions; check actual campus coverage, capture dates, API terms and attributions.
- **UCLA newsroom aerial photos:** https://newsroom.ucla.edu/file?fid=68b0e3ce2cfac25c872c7ea5 . Useful reference images, **not assumed openly licensed for app training or redistribution**.
- **Best validation:** teammates take geotagged, timed photos of 10 selected walkway segments during tomorrow's UCLA walkthrough; compare model state at the *same local time* and retain photos privately with their consent.

## Source decision
1. **First:** UCLA tree inventory measurements **if export/reuse permission is obtained** + OSM walkway/building geometry.
2. **Then:** make a compact raster/shadow model on one 500 m–1 km central-campus corridor; use County canopy once license is cleared as a crown coverage cross-check.
3. **Fallback:** OSM building heights/levels with qualified, explicitly estimated shadows, optional 3DEP point cloud if UCLA coverage resolves quickly.
4. **Do not plan for:** Google Solar runtime. Its standard permitted-use and map-display terms do not fit Mapbox-based shade navigation.

## Provenance rule
Every ingested asset must record `provider`, `source_url`, `capture_date_or_range`, `retrieved_at`, `license_or_permission`, `unit`, `coordinate_reference_system`, `quality`, and `source_file_checksum`. Unknown values should remain `null`, not be guessed.
