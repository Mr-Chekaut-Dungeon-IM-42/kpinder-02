# Pre-PR checklist

Run through this before opening a PR. It's the mechanical procedure behind [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) — if every item here is checked, the PR satisfies the DoD.

- [ ] `git commit` succeeds cleanly (pre-commit hook: lint + format) — no manually-skipped hooks (`--no-verify` is not used).
- [ ] `git push` succeeds cleanly (pre-push hook: backend smoke tests + `uv build`).
- [ ] New or changed endpoints show up correctly in `/docs` (FastAPI's OpenAPI UI) — check it locally, don't assume.
- [ ] Any SQLAlchemy model change has a matching Alembic migration in the same PR, and `alembic upgrade head` applies cleanly from a fresh DB.
- [ ] Any slice this PR touches has unit tests covering the change (repository mocked), not just a passing test suite from before the change.
- [ ] If this PR makes an architectural tradeoff with a real alternative, an ADR is added under `standards/adr/` (see `standards/README.md` for the format) — not every PR needs one, but check before assuming it doesn't.
- [ ] If this PR deliberately doesn't do something the spec implies it should, that's stated in the PR description, not left silent.
- [ ] PR description explains *why*, not just *what* — the diff already shows what changed.
- [ ] Teammate has reviewed and approved (branch protection enforces this, but don't rely on the gate alone — actually read the diff).
