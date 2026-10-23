# Lab 4 audit — CI gate proof, and where the AI's first draft cut corners

Scope: CI (`.github/workflows/ci.yml`), CD (Railway + Vercel native integrations, ADR-0022/0023), the `/version` endpoint, and the ADRs behind each tool choice (ADR-0021–0025). The AI-assisted design interview that shaped these ADRs is in `ai/prompts/` (prompt entries 0007+); this file is the self-audit of that process, plus the hands-on proof that the resulting CI pipeline actually blocks what it claims to.

## Part A — proof the CI gate actually fails on a real violation

Each required job was broken on purpose, locally, running the **exact command the workflow runs**, before ever opening a PR — so the "it blocks a dirty PR" claim in the Definition of Done isn't just asserted, it's demonstrated. (Live Actions run links for the same breakage, from an actual PR, are linked at the bottom once the PR is open — see note at the end of this section.)

### 1. `ruff check` (backend-lint job)

Appended a deliberately broken snippet to `backend/app/main.py`:
```python
import os,sys
x=1;y=2
```
Ran `cd backend && uv run ruff check .` (identical to the CI step):
```
E401 Multiple imports on one line
E402 Module level import not at top of file
I001 Import block is un-sorted or un-formatted
F811 Redefinition of unused `os` from line 1
F401 `sys` imported but unused
E702 Multiple statements on one line (semicolon)
Found 6 errors.
```
Exit code `1` — this is exactly the check the `backend-lint` job runs, so a PR with this diff fails that required check and cannot merge. Reverted before committing anything.

### 2. `pytest` (backend-test-unit job)

Edited `backend/tests/test_version.py` to assert a value the code does not produce (`{"sha": "intentionally-wrong"}` instead of the real fallback). Ran `cd backend && uv run pytest -q` (identical to the CI step):
```
FAILED tests/test_version.py::test_version_falls_back_to_unknown
FAILED tests/test_version.py::test_version_reports_git_sha_override
FAILED tests/test_version.py::test_version_prefers_railway_sha_over_override
3 failed, ...
```
Reverted before committing. (The first attempt at this also caught a real mistake of ours — see Part B, item 2.)

### 3. `eslint` (frontend-lint job)

Appended `const   unused = 1` to `frontend/src/main.tsx`. Ran `cd frontend && npm run lint` (identical to the CI step):
```
src/main.tsx
  11:9  error  'unused' is assigned a value but never used  @typescript-eslint/no-unused-vars
✖ 2 problems (1 error, 1 warning)
```
Non-zero exit — reverted before committing.

### 4. Conventional Commits PR title (pr-title job)

Not reproducible locally without standing up a second GitHub Action run (the `amannn/action-semantic-pull-request` action validates the live PR title via the GitHub API, not a file in the repo). Verified by inspection instead: the action rejects any title that doesn't match the Conventional Commits grammar (`type(scope)?: subject`, type drawn from the configured set — `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, etc.). **Planned follow-up**: the PR that ships this lab's work will itself be opened once with a deliberately non-conventional title (e.g. `"wip stuff"`) to capture a real failing Actions run, then retitled to pass — link added below once done.

### Live Actions run links (added once the PR is open)

- Failing run (dirty PR, pre-fix): `TODO — paste Actions run URL here`
- Passing run (after fixes, pre-merge): `TODO — paste Actions run URL here`

## Part B — corrections to the AI's first draft

1. **`/version` via `git rev-parse HEAD` at runtime was the AI's first suggestion** (lab-3-era code) and looked reasonable until ADR-0023's own context section names the problem: it silently falls back to `"unknown"` if `.git` isn't in the build context, and nothing enforces that it is. The fix (this lab) replaces it with the platform-provided `RAILWAY_GIT_COMMIT_SHA` env var, which Railway's native GitHub integration populates automatically — a documented, stable contract instead of an implicit one. See ADR-0023.

2. **A real mistake caught mid-audit, not a hypothetical one**: while producing the Part A, item 2 evidence above, the restore step used `git checkout -- backend/app/main.py` to revert the intentionally-broken test file's sibling edit. Since the `/version` rewrite itself was still uncommitted at that point, `git checkout --` silently reverted it too, back to the old `git rev-parse` implementation — and the very next test run then failed for the *wrong* reason (a real bug reappearing, not the intentional breakage), which is how it was caught immediately rather than slipping through. Lesson applied: restoring a deliberately-broken file for an audit demo must not use a blanket `git checkout`/`restore` while unrelated uncommitted work sits in the same file — a targeted edit-and-revert (or `cp`/`sed` scoped to the specific change) is the safer idiom, and that's what the rest of this audit's restores used instead (see Part A, items 1 and 3).

3. **E2E as a CI job was initially tempting to skip entirely** ("no e2e test files touch CI-specific infra, so why bother") — but ADR-0025 already commits to running e2e in CI as an advisory (non-blocking) job. Implemented as a `continue-on-error: true` job that brings the stack up via `docker compose` and points the existing black-box e2e suite (`backend/tests/test_e2e_journey.py`, which already skips gracefully if the server isn't reachable rather than failing) at it. This is the most infra-heavy job in the workflow and the one most likely to need follow-up tuning (e.g. the hardcoded loopback IPs in `docker-compose.yml` under ADR-0021 needed explicit `DB_HOST=127.0.0.1`/`APP_HOST=127.0.0.1` overrides in the CI env, since GitHub's Ubuntu runners don't have the `127.0.0.2`/`127.0.0.3` aliases a local dev machine might have configured) — flagged here rather than silently assumed to work on the first real run.

4. **Railway's managed Postgres plugin was the AI's first instinct for the staging DB** (simplest to provision) — ADR-0022 already documents why that was rejected (PostGIS availability isn't guaranteed on that plugin's image) in favor of running the identical `postgis/postgis:16-3.4` image Railway, CI, and local dev all already use. Recorded here only to confirm the audit checked it against the ADR rather than re-litigating it.
