---
name: topic-research
description: Research APIs, datasets, libraries, algorithms, equations, licensing, pricing, or unfamiliar technical claims. Use before relying on an unverified capability, formula, or data source; produce a concise sourced decision and checks, without implementing code.
---
# Research a technical topic
1. State the concrete question and how the answer affects Shady Business. Check `docs/references/` and existing code first; avoid repeat research.
2. Prefer primary sources: official specifications, API docs, source code, authoritative datasets, scientific references. Check dates, versions, permissions, spatial/temporal coverage, costs, and known limits. Cite URLs.
3. For **APIs**, establish authentication, endpoint/schema, limits, quotas, billing, error behavior, licensing, and a no-request validation approach; never call paid/authenticated APIs without permission.
4. For **math/algorithms**, define variables and units, state assumptions, derive or verify formulas, examine boundary cases, complexity, and a worked example; propose reproducible numerical tests. Check peer-reviewed/authoritative references for consequential claims.
5. Compare at most 2–3 viable approaches on correctness, legal usability, engineering effort, data dependencies, and fallback behavior. Label confirmed facts vs hypotheses; report uncertainties rather than guessing.
6. Give a crisp recommendation and one minimal experiment to falsify it. Save a short dated summary in `docs/references/<topic>.md` **only if** likely to be reused; otherwise answer directly.
7. Research does **not** modify runtime code, enable services, fetch restricted datasets, or incur charges. Respect user restrictions on browsing.

**Output:** decision, verified facts/sources, risks, next safe experiment. Keep it brief; don't paste entire external docs.
