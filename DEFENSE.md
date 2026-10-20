# Lab 4 Defense — CI/CD

## Goal

CI that blocks merge into `main` without a green run; CD that auto-deploys every merge to `main` to a staging environment reachable from the internet.

## What CI checks, and why

| Check | Tool | Blocking? |
|---|---|---|
| Backend lint/format | `ruff check` + `ruff format --check` | Yes |
| Backend build | `uv build` | Yes |
| Backend unit tests | `pytest` (repo mocked) | Yes |
| Backend integration tests | `pytest -m integration` against a real `postgis/postgis` service container | Yes |
| Backend E2E tests | `pytest -m e2e` against the app running via `docker compose` | **No** (advisory) |
| Frontend lint/format | `eslint` + `prettier --check` | Yes |
| Frontend build | `vite build` | Yes |
| Commit message convention | Conventional Commits on the **PR title** (squash-merge), via `amannn/action-semantic-pull-request` | Yes |

All of the above run in GitHub Actions (`.github/workflows/ci.yml`) on every PR into `main`. Rationale for GitHub Actions over an external CI system: ADR-0025. Rationale for checking the PR title (not every commit) under squash-merge: ADR-0024.

E2E is advisory, not blocking, because it's the heaviest, most infra-dependent job (brings up the whole stack via `docker compose`) and the project's E2E coverage is still growing — see ADR-0025's job list and `ai/audit/lab-4.md` Part B.3 for the specific wrinkle hit getting it running on GitHub's runners.

## Merge policy

Branch protection on `main`:
- All jobs above except `backend-test-e2e` are **required status checks**.
- The PR branch must be up to date with `main` before merging.
- Direct pushes to `main` are disabled — PRs only.
- **One human approval** is required; self-merge is not allowed (`standards/DEFINITION_OF_DONE.md` item 5).
- Merge strategy: **squash merge**, so `main`'s history is one Conventional-Commits-titled commit per PR.

*(Branch protection is a GitHub repo setting, not a file in this repo — configured at Settings → Branches → `main` once this PR merges and the workflow has run at least once, so GitHub has the check names to offer in the required-checks list.)*

## CD: where and how

- **Backend** → Railway, built from `backend/Dockerfile` via `backend/railway.json` (explicit Dockerfile builder + `/health` healthcheck). A second Railway service runs `postgis/postgis:16-3.4` directly (not Railway's managed Postgres plugin — PostGIS isn't guaranteed there; see ADR-0022) with a volume for persistence.
- **Frontend** → Vercel, building the Vite app via `frontend/vercel.json`.
- Both are connected **directly to the GitHub repo** via their own native integrations — not driven by a deploy step inside the Actions workflow. CI and CD are fully decoupled: CI gates the *merge*; the merge itself (a push to `main`, which only happens after required checks already passed) is what triggers each platform's own auto-deploy. See ADR-0023 for why this was chosen over an Actions-driven `railway up`/`vercel deploy` step.
- Both services' GitHub integration populates the deployed commit SHA as a platform env var automatically (`RAILWAY_GIT_COMMIT_SHA` for the backend).

## `/version`

`GET /version` on the backend returns `{"sha": "<commit sha>"}`, reading `RAILWAY_GIT_COMMIT_SHA` (falling back to a `GIT_SHA` override, then `"unknown"`) — not `git rev-parse HEAD` at runtime, since the running container has no `.git` directory and no guarantee it ever would (ADR-0023). This is what Lab 5's deployment-verification step checks against.

## Audit: does CI actually fail on real violations?

Yes — each required check was broken on purpose and run locally with the exact command CI runs, before ever opening a PR:
- `ruff check` caught a deliberately malformed import block (6 errors, exit 1).
- `pytest` caught a deliberately wrong test assertion (3 failures).
- `eslint` caught a deliberately unused variable (1 error, exit 1).

Full output and the one real mistake this exercise caught along the way (an accidental `git checkout` that silently reverted an uncommitted fix mid-audit) are in [`ai/audit/lab-4.md`](ai/audit/lab-4.md). Live GitHub Actions run links (a genuinely failing PR, then the same PR fixed) are added to that file once the PR for this lab is open.

## Tool choices — see ADRs

- `standards/adr/0021-hostname-isolation-over-port-shifting.md` — standard port 5432 everywhere, hostnames (not ports) separate dev/test/CI databases.
- `standards/adr/0022-railway-vercel-staging-hosts.md` — Railway (backend+DB) / Vercel (frontend), and why not Render/Fly.io/Railway's managed Postgres.
- `standards/adr/0023-native-cd-over-actions-driven-deploy.md` — platform-native CD, `/version` reads an env var instead of shelling to `git`.
- `standards/adr/0024-conventional-commits-on-pr-title.md` — squash-merge + PR-title linting, and why not per-commit linting.
- `standards/adr/0025-github-actions-as-ci-runner.md` — GitHub Actions, the full job list, and why e2e is advisory.

## Known gaps / honest scope cuts

- Branch protection itself is a dashboard setting, applied once this PR's workflow has run at least once (noted above) — not something a file in this repo can assert.
- The E2E CI job is new and the least battle-tested; it's advisory specifically because of that (see `ai/audit/lab-4.md` Part B.3).
- Railway's free tier is a one-time trial credit, not perpetually free (ADR-0022) — accepted for a semester-scoped course project, with Render documented as the fallback if the credit runs out.
