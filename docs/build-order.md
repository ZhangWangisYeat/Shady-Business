# Implementation gates and parallel ownership

## Today: preserve the template; prepare real UCLA geodata

The Expo/Mapbox and FastAPI starters already exist. **Do not redesign or regenerate them.** Use today's setup window to (1) inspect the public UCLA ArborPro inventory and CSV permissions, (2) check current official campus/accessibility map vs OSM pathways, (3) assign source/license owners in `docs/references/ucla-source-manifest.json`, and (4) optionally convert a *permissioned* inventory extract with `scripts/normalize_ucla_trees.py`. See `docs/shade-model-blueprint.md`. These tasks can proceed independently of app polishing.

| Gate | User-visible test | Owner | Dependency |
|---|---|---|---|
| G0 | Install native Shady Business dev build, actual UCLA Mapbox map loads | Mobile | Public Mapbox token + native artifact secret |
| G1 | Search real UCLA POIs, request `POST /api/routes`, draw connected shortest walk | Routing + mobile | Opt-in OSMnx graph download |
| G2 | Color each real edge shade/sun/unknown using audited geometry and timestamp | Geospatial | Building/canopy height coverage |
| G3 | Compare Fastest, Recommended, Most Shade with explicit detour and quality | Routing | Reliable edge shade scores |
| G4 | Confirm, simulate or use foreground GPS, map follow, shade badge, arrive/reset | Mobile | Connected routes |
| G5 | Campus walk validation; improve GPS smoothing and UI | All | G0–G4 |

**Hackathon priority:** finish G0 and prepare a **small, validated** central-campus shade corridor. If an export of UCLA measured tree heights/crowns is available with permission, shade-data preparation can run in parallel with G0/G1 rather than waiting for all app UI work. Currently the app and API source for G0/G1/G4 are scaffolded; G0/G1/G4 are not validated on device. Keep any UI demonstration labeled when no shade observations exist.

**Team integration:** one feature branch per workstream; agree JSON contracts before parallel work; small PRs; use GitHub issues for active ownership. Agents must not force-push or alter teammates' active files without coordination.
