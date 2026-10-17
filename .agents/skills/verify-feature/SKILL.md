---
name: verify-feature
description: Verify a Shady Business change with focused unit, contract, integration, navigation, and end-to-end checks. Use before merging, committing a major slice, or declaring a feature complete; report evidence and blockers concisely.
---
# Verify observed behavior
1. Identify changed files, product gate, and likely failure modes. Run only relevant fast checks first, then broader build/E2E when integration requires it; use repo commands when available.
2. **Routing invariants:** graph-connected walkable geometry, valid endpoints, correct coordinate order/CRS, finite nonnegative weights, fastest duration minimal among candidates, shade detour caps enforced, cold Recommended equals Fastest, consistent segment/route sums, missing shade not treated as shade.
3. **Native-device invariants:** actual Expo development build and Mapbox render, app lifecycle/foreground-only GPS watcher cleanup, offline/no-network state. **Navigation invariants:** permission denial, inaccurate/lost GPS, simulation clearly labeled, map matching, off-route behavior, sun/shade/unknown status updates, and arrival hysteresis/restart.
4. **Software quality:** type errors, schema validation, provider failures/timeouts, security regressions, no committed secrets; check weather/temp and timezone boundaries.
5. Capture only useful failing assertions/log excerpts; don't flood context with full test output. For a failure, give minimal reproduction and root-cause lead; use `debug-issue` when analysis is needed.
6. Report **PASS / FAIL / NOT RUN** for each relevant check. Do not mark a feature complete unless its core user flow actually works; actual phone E2E testing when feasible beats solely static analysis.

**Output:** checks performed, exact failures, user-visible result, and minimal next fix. No untested success claims.
