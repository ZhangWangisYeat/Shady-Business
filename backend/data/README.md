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
`../../docs/shade-scoring.md`; the HTTP route adapter uses this coverage-aware
scorer and falls back to Fastest when its exposure remains incomplete.

Before promoting a local demo corridor, run the read-only gate:

```powershell
python scripts/audit_shade_coverage.py --buildings backend/data/ucla_buildings.geojson --trees backend/data/ucla_trees.geojson --corridor-bbox WEST SOUTH EAST NORTH
```

For a real route, prefer deriving the audit extent from every graph edge eligible
for Recommended and Maximum Shade rather than hand-entering a rectangle:

```powershell
python scripts/audit_shade_coverage.py --buildings backend/data/ucla_buildings.geojson --trees backend/data/ucla_trees.geojson --route -118.4422 34.0728 -118.4440 34.0703 --departure-time 2026-10-17T15:00:00-07:00
```

Exit `0` means both sources explicitly claim verified coverage, all required
dimensions are present, and their coverage polygons contain the proposed
corridor. Exit `1` prints machine-readable blockers and never edits either file;
source/study bounding boxes are not accepted as proof of complete coverage.

Generate an ignored, explicitly unverified on-site checklist only after the
route-aware extent check passes:

```powershell
python scripts/export_field_audit.py --origin-place powell-library --destination-place ackerman-union --departure-time 2026-10-17T15:00:00-07:00 --temperature-c 38 --buildings backend/data/ucla_buildings.geojson --trees backend/data/ucla_trees.geojson --out backend/data/powell_ackerman_field_audit.geojson --confirm-unverified-preview
```

The resulting routes, inspection zone and check points are evidence-gathering
only. The file is never accepted as runtime shade input and never promotes the
coverage flag by itself.

After an independent reviewer fills every object/check-point field and the
top-level `metadata.review` confirmations, validate the packet against the exact
building, tree and graph inputs used to create it:

```powershell
python scripts/validate_field_audit.py --audit backend/data/powell_ackerman_field_audit.geojson --buildings backend/data/ucla_buildings.geojson --trees backend/data/ucla_trees.geojson --graph backend/data/ucla_walk.graphml
```

The validator checks the recorded SHA-256 hashes, the full candidate inspection
scope, all object dimensions/presence, all 15 time-matched observations and
photo references. Exit `0` means only `ready_for_manual_promotion=true`; it never
edits runtime inputs or sets `coverage_complete_verified`. Missing evidence,
model/field disagreement, a recorded obstruction, or changed inputs exits `1`.

Only after that validator passes, create new derived runtime files with an
explicit confirmation (source inputs are never overwritten):

```powershell
python scripts/promote_field_audit.py --audit backend/data/powell_ackerman_field_audit.geojson --buildings backend/data/ucla_buildings.geojson --trees backend/data/ucla_trees.geojson --graph backend/data/ucla_walk.graphml --out-buildings backend/data/ucla_buildings_verified.geojson --out-trees backend/data/ucla_trees_verified.geojson --confirm-promotion
```

The derived files contain the audited candidate bounding box as their explicit
coverage geometry plus the audit/reference hashes. Point `SHADY_SHADE_FILE` and
`SHADY_TREE_FILE` at those files only after reviewing the promotion report. The
tool refuses incomplete evidence, structural edits, changed inputs, source-file
overwrites and existing output paths.

## Existing OSM bundle import

`python scripts/import_osm_buildings.py --input PATH/TO/ucla_osm.json --out backend/data/ucla_buildings.geojson`
converts the earlier Shady Business OSM bundle without network calls. It retains
all footprints but uses only explicitly labeled OSM height tags; default/level
heights become unknown. No guessed tree crowns are imported. Source checksum,
ODbL attribution, fetch timestamp and units are retained. See
`../../docs/references/ucla-data-audit.md` for the local intake results and
minimum fields needed from an authorized tree inventory export.

## Local user-supplied building estimates

To derive the runtime file from the preserved OSM input and the user's 2026-10-17
height table:

```powershell
python scripts/apply_user_building_heights.py --input ucla_buildings.geojson --out backend/data/ucla_buildings.geojson
```

This applies 16 approximate heights as `user_supplied_estimate` and excludes the
three explicitly ignored unnamed roof/tent/shed features from shade obstruction
modeling. It does not change the walking graph or claim field verification, and
keeps `coverage_complete_verified=false` until the corridor/external buffer is
actually checked.

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
