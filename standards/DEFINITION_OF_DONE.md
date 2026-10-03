# Definition of Done

A PR is **done** — mergeable into `main` — when all of the following hold. This is the outcome-level bar; [`CHECKLIST.md`](CHECKLIST.md) is the step-by-step procedure for getting there.

1. **Lint/format clean.** `ruff` (backend) and, once `frontend/` exists, `eslint`+`prettier` report no violations. Enforced automatically by the `pre-commit` hook on every commit.
2. **Tests pass.** Unit tests (repository mocked) for any slice the PR touches, plus the backend smoke test. Enforced automatically on `git push` via the `pre-push` hook; integration tests (real Postgres+PostGIS via testcontainers) run in CI on the PR.
3. **Builds.** `uv build` succeeds for the backend (and once it exists, the frontend build succeeds too). Enforced on `git push` via the `pre-push` hook.
4. **New/changed endpoints are reflected in FastAPI's auto-generated OpenAPI docs.** No endpoint exists that isn't visible in `/docs` — it's the shared API contract between the two of us, not a side document to keep in sync by hand.
5. **Schema changes ship an Alembic migration.** No PR changes a SQLAlchemy model without a corresponding migration in the same PR.
6. **Architectural tradeoffs are recorded.** If the PR makes a decision with a real alternative (not a routine implementation detail), it includes an ADR under `standards/adr/` following the MADR format.
7. **One approval from the other person**, enforced via GitHub branch protection on `main`. Self-merge is not allowed, even for small changes — the point is that someone other than the author reads every slice at least once.

A PR that satisfies all seven can merge. A PR that satisfies some but not all should say explicitly, in its description, which ones it's deferring and why — silently skipping one is not the same as consciously scoping it out (see `ai/audit.md` for how this project tracks deliberate scope cuts at the spec level; the same honesty applies at the PR level).
