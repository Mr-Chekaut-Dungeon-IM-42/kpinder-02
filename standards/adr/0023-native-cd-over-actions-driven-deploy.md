# CD via native platform GitHub integrations, not an Actions deploy step

- Status: accepted
- Date: 2026-10-16

## Context

The task requires: commit to `main` → auto-deploy to staging, with the deployed service exposing `/version` returning the deployed commit's SHA (needed by Lab 5). The current `/version` implementation (`backend/app/main.py`) shells out to `git rev-parse HEAD` at container runtime — fragile, since it silently falls back to `"unknown"` if `.git` isn't present in the running container, and whether it is present depends on undocumented details of however the image got built.

Two ways to wire up CD were on the table: have GitHub Actions explicitly build and push each deploy (via the Railway/Vercel CLIs, with their tokens as GitHub secrets), or connect Railway and Vercel directly to the GitHub repo and let their own integrations watch `main` and deploy on push, independent of the Actions workflow.

Both Railway and Vercel, when deploying via their native GitHub integration, automatically populate the deployed commit SHA as a platform-provided environment variable on the running service (`RAILWAY_GIT_COMMIT_SHA` and `VERCEL_GIT_COMMIT_SHA`, respectively) — no custom CI step is needed to compute or pass it.

## Decision

CD is **platform-native**: Railway and Vercel are each connected directly to the GitHub repo, each deploying independently on push to `main`. No deploy job exists in the GitHub Actions workflow — CI (ADR-0025) is solely a merge gate; it does not perform or trigger the deploy itself.

`/version` is changed (future implementation work, not this lab's ADR-only scope) to read the commit SHA from the platform-provided env var (`RAILWAY_GIT_COMMIT_SHA` on the backend) with a fallback chain ending in `"unknown"`, replacing the `git rev-parse HEAD` subprocess call entirely.

## Alternatives considered

- **Explicit Actions-driven deploy** (`railway up` / `vercel deploy` in a `deploy` job gated behind the CI job, passing `GIT_SHA=${{ github.sha }}` as a build arg): gives a single audit trail (one workflow file, one Actions run log covering lint → test → deploy) and keeps deploy credentials inside GitHub secrets rather than split across two external dashboards. Rejected because it's strictly more moving parts — two CLIs, two sets of deploy tokens as GitHub secrets, a job that must correctly gate on the CI job's success — for a problem (SHA propagation) the platforms already solve natively. For a lab-scoped project, fewer secrets and fewer custom scripts to maintain outweighs having deploy visible in the Actions log.
- **Keep `git rev-parse` at runtime, verify `.git` ships in the image**: rejected — depends on an unverified assumption about Railway's/Vercel's build context, and even if true today, it's an implicit contract nothing enforces going forward. The platform-provided SHA env var is a documented, stable API; `.git`-in-the-build-context is not.

## Consequences

- CI (lint/test/build/commit-convention) and CD (deploy) are fully decoupled: a CI failure on a PR branch has no bearing on deploys, and a deploy is not blocked by, nor does it wait on, the Actions workflow completing — it's triggered purely by the push to `main`, which only happens after the PR's required CI checks already passed (branch protection, ADR/DoD). In practice this means CI gates the merge, and the merge itself is what both triggers CD and guarantees CI was green for that commit.
- Deploy visibility lives in Railway's and Vercel's own dashboards, not in GitHub Actions — anyone auditing a deploy needs to check the platform, not just the repo's Actions tab.
- If backend and frontend ever need to deploy in lockstep (e.g., a breaking API contract change), there's no built-in ordering between the two independent deploys — accepted for now since the API is additive/backward-compatible in practice; would need revisiting if that stops being true.
