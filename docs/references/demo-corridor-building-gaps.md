# Royce–Ackerman building-height gaps — 2026-10-17

Scope: buildings without accepted `height_m` near the bounded Royce Hall →
Ackerman Union candidate graph. This is an OSM tag audit, not field validation.

- The local ODbL extract has 19 unknown building heights. Only way
  [`184444681`](https://www.openstreetmap.org/way/184444681) intersects the
  rectangular envelope of the 622 eligible keyed candidate edges; its footprint
  is approximately 0.36 m from an eligible graph edge.
- The official read-only OSM API currently identifies it as **Engineering VI**
  with `building:levels=5`, but no `height` tag. The existing importer's
  `5 × 3.2 m` value is therefore a clearly labeled estimate, not a measured or
  explicit OSM height and remains excluded from verified sunshine claims.
- Eight other unknown-height ways within roughly 100 m were checked through the
  same official API. None exposed a `height`; examples include roof/tent features,
  Ostin Music Center A/B, Entrepreneurs Hall, Gold Hall, Parking 5 and Young Hall.

Primary source pattern:
`https://api.openstreetmap.org/api/0.6/way/{id}.json`. OSM attribution and ODbL:
[OpenStreetMap copyright](https://www.openstreetmap.org/copyright).

Decision: do not write level/default estimates into `height_m` and do not set
coverage verified. The next safe evidence is a permissioned/field-checked height
for Engineering VI plus confirmation that the proposed corridor's external
shadow-casting buffer contains no unmodeled obstructions.

## Route-aware coverage gate

The Royce Hall → Ackerman Union audit now derives its scope from the real walking
graph rather than a hand-drawn route. At the maximum Recommended detour it covers
369 eligible keyed edges; the larger Maximum Shade bound covers 622 edges and is
therefore used as the common gate. At 2026-10-17 15:00 PDT, the largest modeled
building and tree-shadow reaches are 71.21 m and 62.46 m. Both buffered candidate
areas fit inside the shared local source/study rectangle.

Local transformation accounting is complete: 153 source building footprints
became 150 modeled footprints plus the three explicitly excluded unnamed
roof/tent/shed features; all 20,177 inventory rows are accounted for as 16,553
outside the study rectangle, one non-tree record, and 3,623 modeled trees.

This verifies route scope, input dimensions, transformation accounting and
time-specific source extent. It does **not** prove that OSM or the ArborPro export
contains every real obstruction, nor does it resolve ArborPro redistribution
permission. Consequently both runtime files retain
`coverage_complete_verified=false` and no `coverage_geometry`; the API must keep
sun exposure unknown until independent completeness evidence or a field audit is
available.

### Multiple-origin check at 15:00 PDT

The same spatial gate was run over every unordered pair of the five current POIs.
Six pairs passed the source-extent-plus-shadow-buffer check: Royce–Powell,
Royce–Bruin Plaza, Royce–Ackerman, Powell–Bruin Plaza, Powell–Ackerman and
Ackerman–Bruin Plaza. Every pair involving Engineering VI failed because its
bounded candidate graph and shadow buffer extend south of the local data extent.

An isolated in-memory check temporarily treated the source rectangle as complete
without editing either GeoJSON. At 38°C it found three distinct bounded paths for
Royce–Ackerman, Powell–Bruin Plaza and Powell–Ackerman; Royce–Bruin Plaza had two,
and the two shortest pairs truthfully reused Fastest. All tested modes respected
their duration caps and had zero unknown time under that explicit test-only
assumption. Powell–Ackerman at 10°C also returned Recommended equal to Fastest.
The normal API was then checked without the assumption and correctly returned
unknown exposure with both alternatives aliased to Fastest.

## Subsequent user-directed local estimates

The user subsequently supplied a referenced screenshot table with approximate
heights for all 16 named gaps and explicitly directed the three unnamed
roof/tent/shed features to be ignored as obstructions. The derived, Git-ignored
runtime GeoJSON records these values as `user_supplied_estimate`, `confidence=low`
and `field_verified=false`; it does not alter the preserved input or walking
graph. This resolves numeric model inputs, not coverage completeness or measured
accuracy, so verified sunshine remains disabled.

## Powell–Ackerman field-audit packet

For the strongest current three-route example, the local exporter generated a
Git-ignored field checklist for Powell Library → Ackerman Union at
2026-10-17 15:00 PDT and 38°C. It contains all three candidate route lines, 150
modeled route segments, and 15 field checkpoints (five per mode). Each mode has
at least one modeled-sun and one modeled-shade checkpoint.

The conservative inspection zone covers the bounding box of all 643 edges that
could participate in a Maximum Shade route, which also contains every
temperature-aware Recommended candidate, plus the 71.21 m maximum shadow reach.
It contains 41 modeled building footprints and 1,288 modeled tree points. Every
one of those 1,329 obstruction records has blank
`presence_verified` and `dimensions_verified` fields for an independent reviewer
to complete. All 15 route checkpoints likewise retain blank `actual_state`,
`missing_obstruction`, `photo_reference`, and `notes` fields.

This packet is planning evidence only: its metadata explicitly says
`assumed_coverage_only=true`, `coverage_complete_verified=false`, and
`not_runtime_shade_input=true`. The route API therefore remains fail-closed until
the object inventory and time-matched route observations have actually been
reviewed.

The generated packet now records SHA-256 identities for the building file, tree
file and walking graph. A read-only validator requires all 1,329 object checks,
all 15 time-matched route observations and photos, a complete-zone/outside-caster
review, and source reuse authorization. On the current unfilled packet it
correctly reports `ready_for_manual_promotion=false`; even a fully passing packet
does not mutate runtime coverage and still requires a deliberate promotion step.

That deliberate step is implemented as a separate fail-closed command. It first
re-runs the evidence validator, verifies a structural fingerprint that excludes
only the designated human-entry fields, and writes new derived building/tree
files rather than overwriting their sources. The current packet was exercised
against this command and was correctly refused with no output files created.
