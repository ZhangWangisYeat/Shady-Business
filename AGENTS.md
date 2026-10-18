# Shady Business — Shared Engineering Instructions (native mobile)

## Mission and priority
Deliver a **working UCLA campus walking app** on a real iOS/Android device before polish or experimental AI. Flow: select start + destination → compare **Fastest**, **Recommended**, **Maximum Shade** → confirm → forward-following navigation with current sun/shade/unknown status → arrive → plan another walk. Read `docs/product.md` for observable acceptance criteria. The app is **not** Google Maps or Apple Maps and must not copy branding/assets.

## Stack and sources of truth
- Mobile: **Expo + React Native + TypeScript**, `@rnmapbox/maps` (Mapbox Maps SDK via community-maintained wrapper), Expo development build, `expo-location`, Mapbox Standard style. **Not Next.js, MapLibre GL JS, a WebView, or Expo Go.** Check actual compatible versions before install.
- API/algorithms: Python + FastAPI + Pydantic + OSMnx/NetworkX + Shapely/GeoPandas + Astral or pvlib; Pytest. A small static campus POI index avoids third-party geocoding.
- `docs/product.md`: user-facing states and must-haves. `docs/architecture.md`: boundaries and data/model algorithm. `docs/api-contracts.md`: source of truth for interchange. `docs/decisions.md`: ADRs. `docs/progress.md`: only VERIFIED progress/blockers. `docs/references/`: cited research.
- Client is **presentation and live guidance**; backend owns route and sun calculations. The native map is visualization, **not evidence of building height or real-time shade**.
- API contract: GeoJSON `[longitude, latitude]`; meters; seconds; Celsius; offset-aware ISO 8601 dates; explicit `unknown` (never coerced to shade/zero).

## Engineering rules
1. Inspect `git status`, relevant code/contracts, and owner before editing. Preserve teammates' changes; no force-push, reset, unreviewed lockfile churn, or unrelated refactor.
2. Deliver **vertical slices** with user-observable behavior and explicit acceptance tests. Favor small cohesive modules, typed contracts, SRP/separation of concerns, dependency inversion only at external provider boundaries; no speculative abstraction.
3. **Deterministic domain:** route optimization, sun-angle calculations, temperature policy, time caps, map matching and arrival are testable pure logic; LLMs do not choose routes or pronounce shade certainty.
4. **Geospatial integrity:** pedestrian-only connected edges; validate CRS, POI snapping, edge geometry, hours and daylight saving, plausible speeds, coordinate order, and provider provenance. Missing / imprecise heights, foliage or sidewalk position imply estimated/unknown results, not fabricated confidence.
5. **Provider/legal boundaries:** Mapbox licensed SDK/tiles for display. Do not extract, cache or repurpose proprietary Mapbox cartographic content as your independent shade input. **Google Solar API is not a runtime shade source** without independently obtained written permission for this use, and Solar's map-display policy is incompatible with simply overlaying its data on Mapbox. No Google Solar calls. Respect public OSM/LA County attribution and dataset licenses.
6. **Security & privacy:** request foreground GPS permission only when needed; disclose simulation; do not persist precise location tracks; stop location watcher after arrival/exit; validate bounds and inputs; avoid PII and secrets in logs; least-privilege public Mapbox token, private SDK download tokens only in developer secrets/CI, no hardcoded credentials. Set API timeouts, retry limits, rate limits and CORS.
7. **No surprise spend/deploy:** no paid APIs, SDK billing enablement, deployment, cloud-service changes or real provider calls requiring spend without explicit team approval. Set limits/alerts when enabling services. Backend must work with local deterministic test fixtures.
8. **Test actual behaviors:** Pytest for walking graph, edge time, shadow projection, constrained routing and date/time; Jest/RNTL for mobile screens and navigation state; physical device integration and GPS-denial/accuracy/off-route/arrival cases. Report PASS/FAIL/NOT RUN truthfully.
9. **Communicate contracts early:** amend `docs/api-contracts.md` with both owners when changing JSON schema. Branch by feature, land reviewed tested changes, do not assume Claude/Codex share conversation state.
10. Conclude with working behavior, files touched, checks executed, blockers, next narrow slice. Update docs only at material verified milestones.

## Current pre-hackathon mode (2026-10-17)
**Template/data audit first; no unsolicited frontend/backend rewrites.** Maintain current mobile Mapbox scaffold and FastAPI skeleton without replacing them. Prioritize official campus sources and `docs/references/ucla-source-catalog.md`, `docs/references/ucla-source-manifest.json`, and `docs/shade-model-blueprint.md`. Tree inventory *is now known to include measured height and crown spread*; attempt public export only through supported viewer controls and obtain reuse authorization before exporting/committing the data. LA County 2023 building outline item metadata says **LARIAC Members only**, despite publicly browseable geometry: no bulk download, redistributing or embedding without express permission. USGS 3DEP and OSM provide permitted alternatives subject to respective licenses. Stage the route/shadow engine during LA Hacks after data readiness is checked. Keep `AGENTS.md` as the shared reference; `CLAUDE.md` imports it; skills unchanged.

## Delivery gates
- **G0 Native shell:** development build runs on actual phone, UCLA Mapbox Standard renders, permissions handled, no routing dependency.
- **G1 Routing:** curated campus POIs + **actual walkable** Fastest path rendered; backend/mobile JSON integration.
- **G2 Shade model:** independent, sourced shadow data for selected campus corridor; shade/sun/unknown colored on real pedestrian segments.
- **G3 Choices:** three graph-connected bounded candidate modes; temperature-aware Recommended; cold matches Fastest; no fake unique routes.
- **G4 Navigation:** choose/confirm, native foreground GPS + deterministic simulated walk, camera-following, current sun/unknown state, off-route, arrival/reset.
- **G5 Quality:** real-device demonstration and validations; AI/canopy improvement only after G0–G4 work.

## Team boundaries
- Mobile owner: `mobile/` and screen navigation (including simulation).
- Routing owner: `backend/app/routing/`, POI catalog and API contract.
- Shade/data owner: `backend/app/shade/` and dataset provenance, with routing owner agreeing on edge-score interface.
No parallel writes to shared schema or root configuration without coordination. Use `topic-research`, `plan-feature`, `implement-feature`, `verify-feature`, `debug-issue` skills as appropriate. Canonical `.agents/skills/` mirrors to `.claude/skills/` with `python scripts/sync_skills.py`; run `--check` before commit.

## Run and smoke-test the app locally (Android emulator)
When asked to "run", "start" or "test" the app, follow these steps end to end without re-asking. They were verified on Windows 11 on 2026-10-17. Use PowerShell syntax; on macOS/Linux the SDK path is `~/Library/Android/sdk` or `~/Android/Sdk`. Run the emulator, backend and Metro as **background** processes and verify each with a check command. Never commit `.env`, `mobile/android/`, `backend/.venv/` or `backend/data/*.graphml` (all gitignored).

**1. Prerequisites (check first, install only what is missing).** You need Node 22+ and JDK 17 with `JAVA_HOME` set. You also need the Android SDK at `%LOCALAPPDATA%\Android\Sdk`, with user env `ANDROID_HOME` pointing there and `platform-tools` and `emulator` on the user `PATH`. Append to the user PATH with `[Environment]::SetEnvironmentVariable`; never `setx PATH`, which truncates it. If Android Studio is installed but the SDK folder is missing, its setup wizard never ran. Get the command-line tools from `https://dl.google.com/android/repository/commandlinetools-win-<ver>_latest.zip` and unzip them to `Sdk\cmdline-tools\latest`. Ask the user before accepting SDK licenses (`yes | sdkmanager --licenses`), then:
`sdkmanager "platform-tools" "emulator" "platforms;android-36" "build-tools;36.0.0" "system-images;android-35;google_apis;x86_64"`.
The first Gradle build installs the NDK, CMake and Build-Tools 35 on its own. Check acceleration with `emulator -accel-check`, which should report WHPX on Windows.

**2. Emulator.** If `emulator -list-avds` has no `ShadyPixel`, create it:
`avdmanager create avd -n ShadyPixel -k "system-images;android-35;google_apis;x86_64" -d pixel_8`.
Then set `hw.gpu.enabled=yes`, `hw.gpu.mode=host`, `hw.keyboard=yes` and `hw.ramSize=4096` in `~/.android/avd/ShadyPixel.avd/config.ini`. Mapbox needs the host GPU. Start it in the background with `emulator -avd ShadyPixel -no-boot-anim -no-snapshot`. A cold boot takes about 90 seconds. It's ready when `adb shell getprop sys.boot_completed` prints `1`. Always pass `-no-snapshot`: closing the window saves a quick-boot snapshot, and loading that snapshot left the emulator stuck `offline` at almost 0% CPU for over 10 minutes. If `adb devices` shows `offline` for more than 3 minutes, kill `qemu-system*`, run `adb kill-server`, and cold-boot again.

**3. Backend (port 8000).**
- In `backend/`, create the venv: `python -m venv .venv`.
- Install: `.venv\Scripts\python -m pip install -e ".[dev,ingest]"`.
- Run the tests: `.venv\Scripts\python -m pytest -q`.
- If `backend/data/ucla_walk.graphml` is missing, run `python scripts/fetch_ucla_graph.py --confirm-network` from the repo root with the venv python. This is a free public OSM Overpass request. It can exit 0 without saving when Overpass throttles, so check that the file exists and retry once.
- Serve in the background: `.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Check: `curl localhost:8000/api/health` should return `"dataset_status":"ready"`.

**4. Mobile config.** If `mobile/.env` doesn't exist, copy it from `.env.example`. Set `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`, which is the emulator's alias for the host. `EXPO_PUBLIC_MAPBOX_TOKEN` must be the user's own public `pk.` token; never invent one. Without it the app works but shows "Set EXPO_PUBLIC_MAPBOX_TOKEN…" instead of the map. A Mapbox secret download token was **not** needed for Android. Then, in `mobile/`: `npm install`, `npm run typecheck`, `npx expo-doctor`.

**5. Native build (only on first run, or after native deps or `app.config.js` change).** With the emulator booted, run `npx expo run:android --no-bundler` in `mobile/` (about 10 minutes the first time). It writes the gitignored `mobile/android/` and installs `com.shadybusiness.app`. Otherwise skip straight to step 6.

**6. Metro and launch.**
- Start Metro in the background: `npx expo start --dev-client --lan --port 8081`.
- **Use `--lan`, not `--localhost`.** On Windows `--localhost` binds only IPv6 `[::1]`, and the app then fails with `java.io.IOException: unexpected end of stream on http://localhost…`.
- Check with `curl http://127.0.0.1:8081/status`, which should print `packager-status:running`.
- Forward the ports: `adb reverse tcp:8081 tcp:8081` and `adb reverse tcp:8000 tcp:8000`.
- Open the app: `adb shell am start -a android.intent.action.VIEW -d "exp+shady-business://expo-development-client/?url=http%3A%2F%2Flocalhost%3A8081"`.
- The first Metro run may trigger a Windows Firewall prompt for Node; ask the user to allow it.
- Stopping a wrapper shell doesn't kill Metro's `node.exe`. Free port 8081 by killing the PID from `netstat -ano | findstr :8081`.

**7. Smoke test (G0/G1 behaviors).** Drive the app with `adb shell input tap X Y`, using screen pixels on the 1080×2400 Pixel 8. Check each step with `adb exec-out screencap -p > shot.png`. If the dev-menu sheet appears on first launch, dismiss it. Expected results:
- Before (a), put the emulator on campus with `adb emu geo fix -118.4426 34.0722`. The start box should read **Your location** with a blue dot.
- (a) Tapping the start box and typing `royce` lists Royce Hall above Royce Drive, with "Places © OpenStreetMap contributors". Type with one `adb shell input text` call per letter: Gboard drops the first letters of a fast burst. If text lands in a Google search screen, Gboard's search toggle (magnifier on its floating toolbar) is on; turn it off.
- (b) With the start left as Your location, choose `ackerman` → Ackerman Union. The location prompt appears; tap **While using the app**. A dashed line animates from the blue dot, then three cards of about 5 min appear with **Start**, **Directions** and **Demo walk**. Recommended and Most shade show "same path" and "Sun exposure unknown" until shade data exists. **Directions** lists steps ending "Arrive at Ackerman Union".
- (b2) Change the start to Royce Hall. The sheet shows **Route preview** with Directions only, plus "Walk there from my location".
- (b3) Run `adb emu geo fix -118.4912 34.0195` (Santa Monica), then tap "Walk there from my location". It shows "You're not on the UCLA campus…". Reset the location with the campus `geo fix` above.
- (c) **Demo walk** counts % up, shows "Shade unknown", and ends at "You've arrived ✓".
- (d) **Plan another walk** returns to search.
- (e) Run `adb shell pm revoke com.shadybusiness.app android.permission.ACCESS_FINE_LOCATION`, relaunch and choose a destination. **Don't allow** shows "Location permission denied. Choose a starting point to preview routes instead." with no crash.
- For an allowed-GPS test: `adb shell pm grant com.shadybusiness.app android.permission.ACCESS_FINE_LOCATION`, then `adb emu geo fix -118.4422 34.0729` (longitude first).
- Report each check as PASS/FAIL/NOT RUN. Map rendering is NOT RUN without a token. A physical phone is still required for G0 sign-off.
