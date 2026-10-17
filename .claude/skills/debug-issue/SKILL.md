---
name: debug-issue
description: Diagnose and repair a reproducible bug, broken build, failing test, incorrect route/shade calculation, or navigation regression. Use when expected behavior differs from observed results; make a minimal evidenced fix with a regression test.
---
# Debug with evidence
1. Record expected vs actual behavior, exact reproduction, environment and recent changes. Read the smallest relevant code path; don't dump the entire repo.
2. Reproduce using a focused test, fixture, trace, or isolated script. If reproduction is impossible, state what evidence is missing and instrument minimally without logging precise location histories or secrets.
3. Form 1–3 ranked hypotheses. Test the cheapest discriminating hypothesis first; isolate frontend, API/units, routing graph, shade-data, and GPS state separately.
4. Fix **root cause** with the smallest safe patch. Add a regression test covering the failure and nearby boundary case. Avoid broad rewrites, silent fallback to fake data, or changing contracts without coordination.
5. Run targeted tests plus affected integration checks. If the issue is external data, report provenance/limits instead of hiding it. Stop and explain if unsafe, unlicensed, or paid access would be required.
6. Report cause, patch, validation, and residual risk in a few lines. Update progress only if a milestone/blocker truly changed.
