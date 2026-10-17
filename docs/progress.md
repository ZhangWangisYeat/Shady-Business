# Verified project status — 2026-10-17

## Verified in creation environment
- GitHub-ready directory structure; five canonical portable skills and mirror script.
- FastAPI `/api/health`, `/api/places`, `/api/routes` source code; no hidden mock route fallback.
- Backend policy, graph fixture and API tests: **9 passed** using locally available Python packages.
- Python source syntactically valid; unit tests run without network requests.

## NOT verified / NOT complete
- No downloadable campus OpenStreetMap graph in the ZIP; the route endpoint returns HTTP 503 until fetched.
- Campus POI coordinates need on-the-ground / map verification.
- **New source discovery:** UCLA’s 2025 Urban Forest Management Plan confirms a 2023–2024 field inventory that includes tree height and crown spread. Public ArborPro viewer linked. Also verified county 2024 canopy raster and 2023 building layer with HEIGHT field. **No data were downloaded, licensed for reuse, or ingested into a model.** Building layer metadata states LARIAC Members only; see source catalog.
- No building-height/tree-crown geodata installed in the app; sunlight remains `unknown` until processing/field validation.
- Native Expo / Mapbox dependency installation, Metro build, device rendering and GPS have not been run.
- Algorithm currently searches k shortest travel paths, not all Pareto-optimal shade paths.
- First-person perspective means pitched camera-following map, not Street View; full voice turn-by-turn not implemented.
- GPS off-route/arrival matching is a first-pass prototype requiring smoothing/hysteresis and field testing.

## Focus before tomorrow's hacking
1. Keep frontend/backend **as a template**; avoid refactoring working scaffolds tonight.
2. Open UCLA’s public ArborPro viewer and look for an allowed CSV export of georeferenced height/crown spread; if blocked, request research permission/extract rather than bypassing controls.
3. Inventory source rights, capture years, and on-campus coverage in `docs/references/ucla-source-manifest.json`.
4. Select 2–3 central-campus demo journeys for model evaluation and on-site verification.

## Original next steps (for hackathon)
1. Verify Mapbox credentials, mobile `npm install`, `expo install --fix` and actual native Android/iOS development build.
2. Download and inspect real UCLA graph; manually test campus route connectivity and pedestrian permissions.
3. Verify mobile-to-backend communication and render real route lines.
4. Find/validate independent building and tree heights; score short corridor with provenance and uncertainty.
5. Improve edge segmentation and constrained route candidate coverage; test hot/cold policies with actual known shade.
6. Test on campus with GPS and finish launch experience.
