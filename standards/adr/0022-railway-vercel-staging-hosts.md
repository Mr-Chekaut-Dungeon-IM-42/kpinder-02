# Railway (backend + DB) and Vercel (frontend) as staging hosts

- Status: accepted
- Date: 2026-10-16

## Context

Lab 4 requires a staging environment reachable from the internet, auto-deployed on every merge to `main`, with a `/version` endpoint for Lab 5's deployment-verification step. The team wants free tooling, and the backend has a hard dependency on Postgres **with the PostGIS extension** (ADR-0005, `docker-compose.yml` uses `postgis/postgis:16-3.4`), which most "free Postgres" offerings don't ship by default.

Candidates considered: Railway, Render, Fly.io, and Vercel (frontend only — it doesn't run arbitrary long-lived backend containers or stateful Postgres).

## Decision

- **Backend**: Railway, as a Docker-based service built from `backend/Dockerfile`.
- **Database**: a second Railway service running the `postgis/postgis:16-3.4` image directly (the same image used locally and in CI), with a Railway volume for persistence — **not** Railway's one-click managed Postgres plugin, since that plugin's image is not confirmed to include the PostGIS extension, and using the identical image everywhere (local/CI/staging) removes an entire class of "works here, not there" bugs.
- **Frontend**: Vercel, building the Vite app directly from the repo.
- Both platforms are connected to the GitHub repo via their native integrations (see ADR-0023) rather than driven through custom CI scripting.

Cost: Railway's free tier is a one-time trial credit (~$5), not perpetually free — continued use after the credit is exhausted requires a paid Hobby plan (~$5/mo). This is accepted for a semester-scoped course project; Vercel's free tier for static/Vite frontends has no such time-box.

## Alternatives considered

- **Render** (free web service + free managed Postgres): rejected as the primary pick because Render's free Postgres also doesn't guarantee PostGIS, and free web services sleep after inactivity, which would make `/version` checks (Lab 5) flaky depending on when they're polled. Kept as the documented fallback if the Railway trial credit runs out before the course does.
- **Fly.io**: comparable Docker-based free tier, but requires a payment card on file even for the free allowance and has a less turnkey GitHub-push-to-deploy story than Railway for this use case. Not chosen.
- **Railway managed Postgres plugin**: simpler to provision (one click, no Dockerfile for the DB), but the PostGIS-availability risk was judged not worth the simplicity, given the whole point of staging is to catch exactly this kind of environment drift before Lab 5.

## Consequences

- Two Railway services (app + db) instead of one, and a Railway volume to manage for DB persistence — slightly more setup than the managed-Postgres path, but environment parity with local/CI is exact.
- The team is on the clock with Railway's trial credit; if it's exhausted before the course ends, migrating to the Render fallback (or paying for Railway Hobby) is a known, already-evaluated escape hatch, not a fresh investigation.
- Vercel and Railway are deployed independently, each on its own schedule triggered by its own GitHub integration — there's no single "deploy" step that deploys both atomically (see ADR-0023 for why that's accepted).
