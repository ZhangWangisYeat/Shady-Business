# Shared backend route demo

The building and tree inputs in `backend/data/` are included at the user's
explicit request so teammates can reproduce the shade route demo. Their
`coverage_complete_verified=true` flags are based on the user's assertion for
2026-10-17 at 15:00 PDT, without observation records. This is not independent
field verification. Coverage geometry is the existing study rectangle, not the
whole UCLA boundary. Original source attribution and unresolved redistribution
terms remain in each file's metadata; this inclusion does not establish a license.

From the repository root on Windows:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,ingest]"
cd ..
backend\.venv\Scripts\python scripts/fetch_ucla_graph.py --confirm-network
# Confirm backend/data/ucla_walk.graphml exists; retry once if Overpass throttles.
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The walking graph remains uncommitted. Its public OSM fetch requires network
access; graph changes may alter exact timings. Restart an existing server to
clear cached shade inputs. Remove stale `SHADY_SHADE_FILE` / `SHADY_TREE_FILE`
overrides or point them at the included files.

In another PowerShell window:

```powershell
$body = @{
  origin = @{ coordinate = @(-118.4422, 34.0728) }
  destination = @{ coordinate = @(-118.4440, 34.0703) }
  departure_time = '2026-10-17T15:00:00-07:00'
  temperature_c = 38
} | ConvertTo-Json -Depth 5
$result = Invoke-RestMethod http://localhost:8000/api/routes -Method Post -ContentType 'application/json' -Body $body
$result.conditions
$result.routes | Select-Object mode, duration_s, sun_seconds, same_as
if (@($result.routes | ForEach-Object { $_.geometry | ConvertTo-Json -Compress -Depth 20 } | Select-Object -Unique).Count -ne 3) {
  throw 'Expected three distinct demo routes'
}
```

Verified locally through the API handler with the existing graph: Fastest
284.89 s / 104.1914 sun s; Recommended 309.02 s / 74.4585 sun s;
Maximum Shade 393.68 s / 56.4079 sun s. All have zero unknown seconds.
Recommended minimizes duration plus temperature-weighted sun seconds within
its detour cap; Maximum Shade minimizes sun seconds within its own cap.
At 15 degrees Celsius Recommended intentionally equals Fastest. Three distinct
routes are not guaranteed for other endpoints, departure times or temperatures.
Mobile must send these same inputs to reproduce this demo. Physical-device
and live HTTP end-to-end verification are not claimed by these results.
