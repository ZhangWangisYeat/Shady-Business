# Shady Business 🌳☀️

**UCLA heat-aware walking navigation — mobile-first LA Hacks prototype.**

Shady Business aims to compare three genuine campus pedestrian paths: **Fastest**, **Recommended** (temperature-weighted) and **Most Shade** (capped detour), then guide the walk on a Mapbox native map while describing modeled shade/sun/unknown conditions.

> **State (October 17, 2026):** This is the existing native starter/template, not a deployed or field-validated app. A UCLA-specific shade data plan is now documented using **UCLA’s 2025 Urban Forest Management Plan and tree inventory**, 2024 county canopy classification, OSM and potential USGS lidar. These sources have been discovered, **not imported**. Keep the mobile template stable today; process a small campus corridor and implement route/shade scoring during the hackathon once source access and permissions are checked.

## UCLA campus data: new focused plan

The strongest new lead is UCLA’s [public ArborPro tree inventory](docs/references/ucla-source-catalog.md), whose 2025 management plan documents **measured tree heights and crown spreads**. If the viewer’s CSV export is enabled for the public and UCLA/ArborPro permits reuse, we can model tree shadows around a **specific central-campus walking corridor**, without relying on Google Solar. OpenStreetMap remains the source for footpaths and initially for building footprints.

- [Prioritized source catalog and licensing](docs/references/ucla-source-catalog.md)
- [Machine-readable source manifest](docs/references/ucla-source-manifest.json)
- [Campus-only mathematical shade plan](docs/shade-model-blueprint.md)
- Run `python scripts/source_readiness.py` to see which source files still need to be acquired; **offline** and free.
- Use `python scripts/normalize_ucla_trees.py --help` only **after** receiving a permissioned CSV export and verifying its exact column names and coordinate units.

**Near-term emphasis:** finish the sleek native Mapbox UI template and source audit before expanding backend features. The previous FastAPI and mobile scaffolds are intentionally **unchanged** in this patch.

## Quick start

### 1. Backend (tested locally)

```bash
cd backend
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e '.[dev,ingest]'
python -m pytest -q
```

**Download real UCLA pedestrian paths** (contacts public OpenStreetMap/Overpass):

```bash
cd ..
python scripts/fetch_ucla_graph.py --confirm-network
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit `http://localhost:8000/api/health`, `/api/places`, and `/docs`. The graph is ignored by Git; any real route requires a graph downloaded by the user. Place coordinates are starter estimates and should be checked on the loaded network and on campus.

### 2. Mobile (native development build; NOT Expo Go)

From the repo root, using Node 22+:

```bash
cd mobile
npm install
npx expo install --fix
npx expo install @rnmapbox/maps expo-dev-client expo-location expo-status-bar
cp .env.example .env  # Windows: copy .env.example .env
```

Put a **public** `pk.*` Mapbox token and the **LAN IP** of the backend in `mobile/.env`. The phone cannot reach a computer's backend through `localhost`. Check `http://YOUR_LAN_IP:8000/api/health` from your phone browser.

Configure the Mapbox **native SDK download credential** using the provider's recommended EAS secret or per-developer `.netrc`/Gradle setup, **not** in the committed repo or a public build-time app config. Do not commit `sk.*` credentials. See [RNMapbox installation instructions](https://rnmapbox.github.io/docs/install) and [download token caveats](https://rnmapbox.github.io/docs/RNMapboxMapsDownloadTokenDetails).

```bash
npx expo run:android  # Android SDK/Android Studio setup required
# or: npx expo run:ios  # macOS + Xcode required
npx expo start --dev-client
```

**These install/build commands have not been executed in this environment**; version compatibility and device rendering are the first gates for the team. Expo SDK 57 is selected as a conservative stable target; use `expo install --fix` and commit the resolved lockfile once one teammate has a successful development build.

### 3. Try the flow

- Select two UCLA landmarks.
- Calculate from a real OSM downloaded walking graph.
- Compare Fastest / Recommended / Most Shade; they legitimately overlap until shade data is processed.
- Choose **Demo walk** to simulate position without location permission, or **Start guided walk** for foreground GPS.
- On arrival, reset to search.

The demo walker does **not** simulate sunlight: the badge remains **Shade unknown** unless independently sourced, analyzed geometries are available.

## Repository layout

```text
AGENTS.md                    # Canonical rules for Codex and team
CLAUDE.md                   # Imports @AGENTS.md for Claude Code
.agents/skills/             # Five canonical, reusable SKILL.md workflows
.claude/skills/             # Bit-for-bit mirrored skills for Claude Code
scripts/sync_skills.py      # python scripts/sync_skills.py [--check]
scripts/fetch_ucla_graph.py # Opt-in OSM network download
mobile/                     # Expo / React Native / Mapbox mobile scaffold
backend/                    # FastAPI / walking graph / shade / policy
backend/tests/              # Offline deterministic tests
docs/                       # Requirements, architecture, contracts, decisions, status
.github/workflows/          # Backend CI + skill synchronization
```

## How routes work

The backend reads a **real** UCLA pedestrian network from an OSMnx-generated GraphML file. It computes connected candidate paths, measures durations, and optionally intersects pedestrian segments with model-generated shadow polygons from **vetted** building footprints and heights. Cold temperature sets the Recommended route to Fastest; warmer conditions increase the allowed trade-off between travel time and direct-sun seconds. The maximum-shade route has a strict walking-time detour cap.

**Current limitation:** candidate paths are from a k-shortest-by-distance search, **not** a guaranteed global minimum exposure. Unknown or incomplete shade measurements are never interpreted as zero sunlight. You must complete [shade model validation](docs/architecture.md) before claiming a genuinely shade-optimized product.

## Cost and data

- Mapbox Maps SDK: published mobile free tier, usage-based thereafter; monitor the account dashboard. Different Mapbox APIs have separate pricing.
- No Google Solar API calls: terms restrict it to energy use cases; its standard map-display requirements are not compatible with this custom Mapbox map workflow.
- OSM requires attribution and adherence to the ODbL; OSM servers should not be used abusively. Evaluate building/tree imagery licensing separately.
- No credentials, native SDK artifacts, downloaded OSM graphs, or precise GPS traces are committed.

## Shared Claude / Codex workflow

`AGENTS.md` governs architecture and quality; `CLAUDE.md` imports it. Codex loads `.agents/skills`; Claude Code loads `.claude/skills`. Edit only canonical skills and run `python scripts/sync_skills.py`, then `python scripts/sync_skills.py --check`. Work in feature branches; use `docs/api-contracts.md` when coordinating client/backend changes. No autonomous force-push or surprise paid API requests.

See [build order](docs/build-order.md), [current verified status](docs/progress.md), [API contract](docs/api-contracts.md), and [UCLA data source catalog](docs/references/ucla-source-catalog.md).
