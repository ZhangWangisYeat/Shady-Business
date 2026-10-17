---
name: plan-feature
description: Plan a nontrivial Shady Business feature, architecture change, or cross-team integration as the smallest testable vertical slice. Use when scope spans multiple modules, dependencies, or API boundaries; skip ceremony for trivial edits.
---
# Plan the smallest deliverable
1. Read only relevant `AGENTS.md` sections, product gate, API contract, current implementation, and `docs/progress.md`; inspect `git status` and teammate ownership.
2. Define observable user behavior, *specific acceptance tests*, non-goals, dependencies, and data provenance. Identify the earliest working increment, not the ideal future architecture.
3. Evaluate failure paths (no route/data, unknown shade, GPS denied, provider errors), security/privacy/license risks, **native Expo build compatibility**, public-vs-secret map tokens, and impact on existing contracts.
4. Choose the simplest maintainable design: cohesive single-purpose modules, explicit contracts, dependency inversion for external providers, minimal dependencies; apply SOLID/DRY only where complexity warrants.
5. Write a 3–7 step plan with affected files, ownership, tests and checkpoints; parallelize only truly independent work. Identify one fallback if external data is unavailable.
6. **Proceed with implementation** if the user asked to build it; don't block on a plan approval unless a destructive action, paid service, legal conflict, or product-direction choice cannot be safely resolved.

**Output:** short plan, acceptance criteria, risk/fallback. No speculative lengthy design document unless requested.
