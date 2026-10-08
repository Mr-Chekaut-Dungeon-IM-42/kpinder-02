# 0004 — Lab-3 Testing-Strategy Interview (`/grill-me`)

Session: a `/grill-me` run over the lab-3 brief (unit + integration + E2E + mutation testing; audit top-3 "green tests miss real bugs"; `DEFENSE.md` + `make mutation`). No test code written this session — only tooling/strategy decisions, since no slice from lab-2 has been implemented yet.

---

**[0004.1]** Prompt: lab-3 brief, pasted in Ukrainian — unit/integration/E2E/mutation testing, audit of weak tests, `DEFENSE.md` + reproducible mutation run. *"what could be done here"*
- **AI Action**: Checked repo state — only `backend/app/main.py`'s health check exists; none of lab-2's slices (`auth`/`matching`/`chat`) have been implemented (confirmed via `git log`/`git show` on the `feat(lab-2): init` commit — docs/ADRs only, no code). Asked whether lab-3 should start with implementing lab-2's design (so there's real branch logic to test) or something smaller.
- **User**: neither — just write an ADR on testing tools now; actual implementation (and tests) wait until lab-2 is built.

**[0004.2]** Prompt (AskUserQuestion): mutation tool — mutmut vs cosmic-ray (Stryker/PIT ruled out, wrong language).
- **User**: mutmut (**AI's recommendation**).

**[0004.3]** Prompt (AskUserQuestion): what "E2E" means given no frontend exists.
- **User**: black-box API-level full user-journey tests, not browser automation (**AI's recommendation**).

**[0004.4]** Prompt (AskUserQuestion): how integration and E2E differ mechanically, not just in scope.
- **User**: integration = in-process ASGI (`httpx` `ASGITransport`) + real testcontainers Postgres; E2E = real running server via `docker compose`, driven over actual HTTP/WS (**AI's recommendation**).

**[0004.5]** Prompt (AskUserQuestion): which module anchors "full coverage of ≥1 module."
- **User**: `matching/service.py` — swipe→match logic (**AI's recommendation**), for its branch richness and direct tie to the mutation-testing/audit requirements.

**[0004.6]** Prompt (AskUserQuestion): mutation testing in CI on every PR, or manual/local only.
- **User**: manual only, via `make mutation` (**AI's recommendation**) — not a CI gate.

**[0004.7]** Prompt (AskUserQuestion): WS testing tooling across tiers, given chat's live-push behavior and `httpx` having no WS support.
- **User**: Starlette `TestClient.websocket_connect` for integration, real `websockets` client for E2E (**AI's recommendation**).

**[0004.8]** Prompt (AskUserQuestion): bundle today's decisions into one "testing strategy" ADR, or one ADR each.
- **User**: one ADR per decision, consistent with lab-2's precedent.

**[0004.9]** Prompt: implicit (user had already said "write tests after finishing lab-2").
- **AI Action**: Wrote `standards/adr/0015` (mutmut) through `0019` (WS test tooling); added spec.md §6 "Testing strategy" (tier definitions, the `matching/service.py` anchor module, the audit/`DEFENSE.md` tie-in) and renumbered the two sections after it; logged this file. No test code, `Makefile` target, or dependency additions were made — explicitly deferred until lab-2's scenarios exist to test. `DEFENSE.md` left untouched, same as lab-2's precedent.
