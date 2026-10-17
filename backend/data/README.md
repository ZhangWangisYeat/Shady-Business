# External local geodata — NOT COMMITTED

- `ucla_walk.graphml`: download with `python scripts/fetch_ucla_graph.py --confirm-network` after installing `backend[ingest]`.
- `ucla_buildings.geojson`: **optional** curated and license-cleared GeoJSON FeatureCollection in WGS84, with `height_m` numeric property on each verified building polygon. Never assume every campus building has an OSM height.
- Include top-level `metadata.data_as_of` only when supported by a source. `metadata.coverage_complete_verified: true` must only be set after verifying that the study corridor has comprehensive modeled obstruction coverage; otherwise absence of mapped shade is **unknown**, not sun. Timestamp of download is not a guarantee of date surveyed.
- Building-only shadows may miss tree shade; the level-ground extrusion model is approximate. Model should mark unverified regions as unknown.

Never commit private location data or restricted/licensed imagery.

## UCLA-first data intake plan (2026-10-17)
Reference `../../docs/references/ucla-source-catalog.md` and `../../docs/shade-model-blueprint.md` before creating local data files. Do not commit ArborPro exports, LARIAC rasters/buildings or other datasets until their *specific* downstream license is known.

Potential local asset, **only with authorization**: `ucla_trees.geojson` built from measured tree heights/crown spread via `python scripts/normalize_ucla_trees.py --help`. Preserve capture date, explicit measurement units, original CSV checksum and any license note in a nearby private provenance record.

Until the shade model has a verified measured input, route rendering may work but predictive sun/shade segments remain unknown. Use campus field photos with timestamps for ground truth, not to infer exact heights.
