# 0007 — Lab-5 Performance/Extraction Interview (`/grill-me`)

Session: a `/grill-me` run over the lab-5 brief (load scenarios in `spec.md`; Lighthouse/web-vitals; profiler + load test with baseline/percentiles; DB `EXPLAIN ANALYZE`; extract the worst module into a library with DI + typed contract; audit top-3; `DEFENSE.md` + `adr/` + `make load`/`make profile` + `/version`). Before asking anything, the AI read `spec.md`, `DEFENSE.md`, all existing ADRs, and the backend/frontend source (notably `app/matching/queries.py`/`repository.py`) to ground its questions in the actual codebase rather than generic lab boilerplate.

---

**[0007.1]** Prompt (AskUserQuestion): the brief's "typed public contract (JS → TS)" instruction doesn't literally apply — backend is Python, frontend is already TS.
- **User**: extraction target should be a backend Python module, with a typed contract via Python type hints/Protocols — treat "JS→TS" as generic lab boilerplate (**AI's recommendation**).

**[0007.2]** Prompt (AskUserQuestion, batched): load-test tool, and profiler.
- **User**: Locust (**AI's recommendation**) for the load tool; py-spy (**AI's recommendation**) for the profiler.

**[0007.3]** Prompt (AskUserQuestion, batched): test environment (local vs Railway staging), and DB seeding scale.
- **User**: local `docker-compose`, not staging — Railway's trial credit is a documented scarce resource (**AI's recommendation**); ~50k seeded users (**AI's recommendation**) — large enough for the planner to make real index choices, small enough to seed in ~1 minute.

**[0007.4]** Prompt (AskUserQuestion, batched): which frontend pages to Lighthouse-audit, and what the load scenario should represent.
- **User**: all four authenticated pages (Feed/Matches/Chat/Profile) — **against the AI's recommendation** of Feed-only, for a fuller picture. Weighted mixed journey (feed/swipe dominant, matches/chat occasional) for the load scenario (**AI's recommendation**).

**[0007.5]** Prompt (AskUserQuestion, batched): how to physically package the extracted library, and how deep the DI should go given ADR-0019 already does constructor-injected concrete infra.
- **User**: `libs/<name>/` as its own `uv` package at the repo root (**AI's recommendation**), not nested under `backend/`. DI should go one level deeper than ADR-0019 — the library defines its own abstract ports (Protocol/ABC), with the backend supplying concrete adapters (**AI's recommendation**) — not just "constructor-injected `AsyncSession`," which doesn't actually make the module infra-agnostic.

**[0007.6]** Prompt (AskUserQuestion): whether `DEFENSE.md` should be replaced per-lab (matching lab-4's precedent) or made cumulative across all labs.
- **User**: replace with lab-5 content (**AI's recommendation**), same pattern as lab-4 replacing lab-3.

**[0007.7]** Prompt (AskUserQuestion): execution mode — run everything autonomously, pause after every step, or run through to the data point (seed+load+profile+DB analysis) and pause there specifically, since the extraction target should follow the data rather than be picked upfront.
- **User**: run it all now, check in once real baseline/profiling numbers exist, then pick the extraction target together before continuing (**AI's recommendation**).

**[0007.8]** Implicit (branch/PR scope).
- **AI Action**: Stated the plan would continue on the existing `feat/lab-5` branch into one PR against `main`, matching labs 1-4's pattern — not asked as a question since there was only one reasonable path (the Agent tool's own rule against asking single-option "questions").

**[0007.9]** Prompt: none — summary handoff.
- **AI Action**: Summarized the full shaped plan (spec.md load-scenario section, Lighthouse audit, measurement, extraction, audit, ADR, DEFENSE.md, Makefile targets) and began executing immediately per [0007.7]'s agreed execution mode. See `0008-lab5-load-test-profiling-and-extraction.md` for what followed.
