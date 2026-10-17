# External local geodata — NOT COMMITTED

- `ucla_walk.graphml`: download with `python scripts/fetch_ucla_graph.py --confirm-network` after installing `backend[ingest]`.
- `ucla_buildings.geojson`: **optional** curated and license-cleared GeoJSON FeatureCollection in WGS84, with `height_m` numeric property on each verified building polygon. Never assume every campus building has an OSM height.
- Include top-level `metadata.data_as_of` only when supported by a source. `metadata.coverage_complete_verified: true` must only be set after verifying that the study corridor has comprehensive modeled obstruction coverage; otherwise absence of mapped shade is **unknown**, not sun. Timestamp of download is not a guarantee of date surveyed.
- Building-only shadows may miss tree shade; the level-ground extrusion model is approximate. Model should mark unverified regions as unknown.

The new independent scorer additionally requires an explicit WGS84
`metadata.coverage_geometry` Polygon/MultiPolygon before declaring uncovered
pieces sunny. The completeness flag alone does not establish a region. Missing
building heights disable verified sunshine claims. Coverage verification must
include trees and outside obstacles casting shadows inward. See
`../../docs/shade-scoring.md`; the legacy HTTP route adapter is not yet migrated.

## Existing OSM bundle import

`python scripts/import_osm_buildings.py --input PATH/TO/ucla_osm.json --out backend/data/ucla_buildings.geojson`
converts the earlier Shady Business OSM bundle without network calls. It retains
all footprints but uses only explicitly labeled OSM height tags; default/level
heights become unknown. No guessed tree crowns are imported. Source checksum,
ODbL attribution, fetch timestamp and units are retained. See
`../../docs/references/ucla-data-audit.md` for the local intake results and
minimum fields needed from an authorized tree inventory export.

Never commit private location data or restricted/licensed imagery.

## UCLA-first data intake plan (2026-10-17)
Reference `../../docs/references/ucla-source-catalog.md` and `../../docs/shade-model-blueprint.md` before creating local data files. Do not commit ArborPro exports, LARIAC rasters/buildings or other datasets until their *specific* downstream license is known.

Potential local asset, **only with authorization**: `ucla_trees.geojson` built from measured tree heights/crown spread via `python scripts/normalize_ucla_trees.py --help`. Preserve capture date, explicit measurement units, original CSV checksum and any license note in a nearby private provenance record.

Until the shade model has a verified measured input, route rendering may work but predictive sun/shade segments remain unknown. Use campus field photos with timestamps for ground truth, not to infer exact heights.

## Local ArborPro crown input (implemented)

The user-authorized local CSV from **查找 UCLA 植被数据** is normalized with:

```powershell
python scripts/import_arborpro_trees.py --csv ../arborpro-inspect/ucla_tree_inventory.csv --bbox -118.448 34.0675 -118.438 34.0755 --out backend/data/ucla_trees.geojson
```

The existing study rectangle yields 3,623 standing-tree records with height and
crown spread. This is not a verified campus property boundary/completeness claim.
Heights/spread feet become meters/radius meters. IDs, source checksum and units
are preserved; stumps/vacancies are excluded and missing dimensions stay unknown.
`SHADY_TREE_FILE` overrides the default local tree file. `load_model()` combines
it with buildings; restart a running server after file updates. Never commit
the CSV, normalized GeoJSON, source JSON or validation output without resolving
redistribution terms. See `../../docs/tree-shade-integration.md` for model limits.
