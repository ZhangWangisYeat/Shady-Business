@AGENTS.md

# Claude Code
Use `AGENTS.md` as the shared source of truth alongside Codex. Claude-only notes: avoid reading the entire `docs/` tree; load the relevant skill and contract for each task. The app uses a native Expo **development build**, not Expo Go. Do not introduce a web frontend by default.

## Running the app (Claude Code)
When asked to run, start or test the app, follow **"Run and smoke-test the app locally"** in `AGENTS.md` step by step:
- **Long-running processes:** start the emulator, uvicorn and Metro with `run_in_background`. Use an `until …; do sleep 1; done` check (boot_completed, `/api/health`, Metro `/status`) instead of plain sleeps.
- **Native build:** run `expo run:android` in the background with output redirected to a log in the scratchpad. Watch it with a Monitor that greps `BUILD SUCCESSFUL|BUILD FAILED|What went wrong|401`.
- **Screenshots:** save `adb exec-out screencap -p` captures to the scratchpad and look at them with the Read tool. Images are shown scaled, so map coordinates back to 1080×2400 before tapping.
- **Shell:** use the Bash tool for adb/emulator commands (Git Bash). Use PowerShell only for user env vars and killing stray `node.exe`.
- **Permissions:** the user has to approve SDK license acceptance and the Windows Firewall prompt themselves. The Mapbox `pk.` token comes from the user and is never generated or committed.

## Campus search and route preview (added 2026-10-17)
The search screen works like Google/Apple Maps, limited to UCLA:
- **Search card (top):** `mobile/src/search/PlaceSearch.tsx`. It has Start and Destination fields, a swap button and a dropdown that queries `GET /api/places?q=` 150 ms after typing stops (only the newest response is shown). Picking a start moves focus to the destination. Leaving a field without picking puts its previous selection back. The bottom sheet hides while a field is focused so the keyboard doesn't cover the results.
- **Auto routing:** `mobile/App.tsx` requests routes as soon as both ends are set or the temperature changes. Rapid changes collapse into one request after 250 ms, and the search animation shows for at least 700 ms. Stages are `plan → navigate → arrived`. Within `plan`, the sheet shows "Where to?", then "Finding walking routes…", then the route cards with Start / Directions / Demo walk, then a directions list.
- **Map:** `mobile/src/map/ShadyMap.tsx`. While routing, it shows a "marching ants" dashed line between the start and end markers. The chosen route then draws itself in (`revealSegments` in `routeDrawing.ts`, about 900 ms ease-out), and other distinct routes appear in grey. The camera is set by hand with `setCamera` whenever the view changes. Declarative `<Camera>` props didn't re-fit when the sheet grew, which hid the route. The Mapbox logo and attribution are moved above the sheet because they must stay visible.
- **Place data:** `backend/app/places/ucla_places.json` holds about 400 named OpenStreetMap features inside the UCLA boundary (ODbL; show "© OpenStreetMap contributors"). To rebuild it, run `python scripts/fetch_ucla_places.py --confirm-network` with the backend venv (one free Overpass request). `--input saved.json` re-normalizes a saved response offline. Normalization and the skip and category rules are in `backend/app/places/osm_import.py`, and ranking is in `catalog.py`. Don't use Google/Apple place data (their terms forbid it) or Mapbox Search (billable). See ADR-009.
- **Directions:** `backend/app/routing/directions.py` builds `steps` from OSM edge `name`/`highway`. Tests are in `backend/tests/test_directions.py` and `test_places.py`. During navigation the sheet shows the next step via `mobile/src/navigation/steps.ts`.
- **Known gaps:** pins are building centers rather than entrances, so routes can loop around a large building (e.g. Royce Hall). There is no "use my location" as start yet. iOS top inset is a fixed 50 until `react-native-safe-area-context` is added in a native rebuild.
