---
name: implement-feature
description: Implement an approved, scoped Shady Business feature end to end across frontend/backend/data boundaries, following repo contracts, secure coding, modular design, and focused tests. Use for coding changes and integration work, not pure research.
---
# Implement a working vertical slice
1. Inspect relevant source, contract, tests, and `git status`; avoid writing into another agent's active files without coordination.
2. For substantial changes, apply `plan-feature` reasoning briefly, then build the smallest observable behavior. Prefer existing patterns and libraries before inventing frameworks.
3. Keep React Native screens, Mapbox adapter, HTTP schemas, domain logic, algorithms, and providers separate. Expo native map requires a development build, NOT Expo Go. Favor SRP, explicit types, narrow interfaces, testable pure calculations, and limited coupling; no speculative factories or generalized frameworks.
4. Make **correctness and security** explicit: input schema/bounds, coordinate order/CRS, temporal timezone, foreground GPS permission and teardown, public-vs-secret Mapbox token handling, provider timeouts, least privilege and no location logging.
5. Never fabricate routes, coordinates, weather, or shade as real. Keep demo fixtures isolated/labeled; unknown shade stays unknown. Routing and temperature policy must be deterministic, not delegated to an LLM.
6. Add focused tests for normal, boundary, and failure cases; include integration tests when contracts change. Verify that data shapes, units, and navigation state agree across the frontend/backend boundary.
7. Run relevant tests/typecheck/lint; fix failures caused by the change. Update `docs/api-contracts.md`/`docs/decisions.md` only if behavior/decisions change; `docs/progress.md` only after a verified milestone.
8. Finish with changes, checks actually executed, limitations, and next integration step. Do not claim success based only on generated code.

**Never:** expose keys, make unauthorized billable calls, force-reset branches, or replace the functional MVP with an unverified redesign.
