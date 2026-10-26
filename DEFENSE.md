# Lab 5 Defense — Performance, Profiling & Extraction

## Goal

Measure the system under realistic load with real percentiles, find the actual bottleneck with real numbers (not a guess), localize and protect it behind a clean module boundary with typed DI, and audit the result honestly — including what the extraction does *not* fix.

## Setup

- Local `docker-compose` Postgres+PostGIS, seeded with **50,000 users** (~2M swipes, 305 matches, ~2.9k messages) via `make seed-load` (`backend/scripts/seed_load_data.py`).
- Load generator: **Locust**, weighted mixed journey (`backend/loadtest/locustfile.py`) — feed/swipe dominate, matches/chat occasional, matching real swiping behavior (spec.md §9 has the exact weights).
- Profiler: **py-spy** (`make profile`) for CPU/wait flamegraphs; direct `time.process_time()` instrumentation as the fallback where `sudo` (required to attach on macOS) wasn't available non-interactively in this environment — see `ai/audit/lab-5.md` Part B.2 for why that substitute is trustworthy here.
- Everything run locally, not against Railway staging — its trial credit is a documented scarce resource (ADR-0022), not something to spend on load testing.

Full methodology, every number below, and the frontend audit are in [`ai/audit/lab-5.md`](ai/audit/lab-5.md). This file is the summary; that file is the evidence.

## Baseline and bottleneck

| | Uncontended | 150 concurrent |
|---|---|---|
| `GET /matching/feed` | p50 32ms / p95 63ms | p50 430-520ms / p95 900-1100ms / p99 1500-1900ms |

A 15-20x blowup, **not** explained by DB connection pool size (10x bump made no measurable difference) and **not** explained by a missing index (`EXPLAIN ANALYZE` confirms the GiST index on `location` is used correctly, ~73ms DB-side). The actual cause: `GetFeedQuery` fetches `limit=500` full `User` rows per request and decodes all of them — measured at ~10-18ms of real, synchronous CPU time per request, on the single uvicorn event-loop thread every other concurrent request shares. At 150 concurrent requests that's ~1.5-2.7s of CPU demand against one effective core, which is exactly the queueing collapse measured.

A second real bug was found and is **not** the extraction target: `auth.LoginCommand` calls Argon2 verification synchronously inside an `async def`, blocking the entire process under concurrent logins (removing login from the load mix roughly doubled throughput). It's real and worth a follow-up one-line fix, but there's no module boundary to draw around it — the brief asked for one module to extract, and `matching`'s feed path is the one rich enough (repository + algorithm + DI) to be a meaningful extraction, independently confirmed as the one whose *design*, not configuration, causes the degradation.

## Extraction: `libs/matching-core`

- New package, `libs/matching-core/`, own `pyproject.toml`, installed by the backend as a local editable path dependency.
- **Zero SQLAlchemy/asyncpg/geoalchemy2/FastAPI imports** anywhere in its source — it depends on its own `Protocol`s (`CandidateRepository`, `PhotoUrlResolver`), defined in `matching_core/ports.py`.
- `FeedService` (the extracted `GetFeedQuery`) raises its own typed errors (`CallerNotFoundError`, `LocationRequiredError`) instead of `HTTPException`.
- `app/matching/adapters.py` is the only file in the backend that imports both `matching_core` and SQLAlchemy — it implements both ports against the real DB/R2 storage.
- `app/matching/queries.py`'s `GetFeedQuery` is now a ~40-line adapter: wire the service, call it, translate the two typed errors to the two HTTP statuses the API contract already promised.
- **Behavior-preserving, not a fix**: the 500-row fetch limit and the ranking algorithm are unchanged. This ADR protects the bottleneck behind a boundary that makes it independently testable and benchmarkable; it does not resolve the latency itself. See ADR-0026 "Known gaps" and the audit's top-3 for what the actual fix would be.

Full design rationale and alternatives considered: `standards/adr/0026-matching-core-extraction.md`.

## Testing

- `libs/matching-core/tests/` — full branch coverage of `FeedService` using **in-memory fakes** for both ports. No Postgres, no FastAPI, no SQLAlchemy mocking.
- `app/matching/tests/test_feed_adapter.py` — covers only the adapter glue left in the app (error translation, schema mapping).
- Full backend suite re-run after the extraction: 82 unit tests, 7 integration tests (real Postgres+PostGIS), 1 E2E journey — all pass unchanged. The live `/matching/feed` endpoint was also hit directly against the 50k-seeded DB post-extraction and returns identical shapes/behavior to pre-extraction.
- `backend/pyproject.toml`'s `[tool.mutmut]` config updated to stop targeting `app/matching/queries.py`'s (now-removed) feed logic. `libs/matching-core` is not yet mutation-tested — recorded as a known gap, not silently dropped.
- New required CI job, `matching-core-test` (`.github/workflows/ci.yml`), lints and tests `libs/matching-core` on its own — it's a separate package, so it needed its own gate rather than riding along inside the backend's existing jobs.

## Frontend audit (Lighthouse)

All four authenticated pages (Feed/Matches/Chat/Profile), production build (`vite build && vite preview`), real authenticated session:

| Page | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|
| Feed | 0.95 | 0.92 | 1.00 | 0.83 |
| Matches | 0.98 | 0.92 | 1.00 | 0.82 |
| Chat | 0.96 | 0.92 | 1.00 | 0.83 |
| Profile | 0.96 | 0.93 | 1.00 | 0.83 |

Findings (not fixed — out of scope for this lab's extraction, recorded for the record):
1. Brand color `#e8457a` fails WCAG AA contrast (3.77:1, needs 4.5:1) on nav links, logout button, and the Feed "Like" button — one shared value, every page.
2. No `<main>` landmark on any page.
3. No meta description in `index.html` (flat SEO score across pages).

## Top 3 (full detail in `ai/audit/lab-5.md` Part D)

1. `matching.GetFeedQuery`'s over-fetch-and-decode-in-Python design — localized and protected, not yet fixed.
2. `auth.LoginCommand`'s blocking Argon2 call — real, found, not extracted (no boundary to draw), flagged for a follow-up.
3. Frontend color-contrast failure on the shared brand color — one root cause, four pages.

## Infra change this lab requires (manual, one-time)

Extracting `libs/matching-core` as a local uv path dependency means `backend/Dockerfile` now needs the **repo root** as its Docker build context (to see `../libs/matching-core`), not `backend/` alone. `docker-compose.yml` and the repo-root `railway.json` (moved from `backend/railway.json`) were updated to match, and `make load`/CI's e2e job (which already builds via `docker compose up -d --build backend` from the repo root) pick this up automatically. The one thing that can't be expressed as a file in this repo — same category as lab-4's branch protection setting — is **Railway's dashboard**: the backend service's **Root Directory** must be changed from `backend` to `/` (repo root) once this PR merges, or the next Railway deploy will fail to find `libs/matching-core`.

## Known gaps / honest scope cuts

- The feed endpoint's actual latency under load is unchanged by the extraction — it was scoped as behavior-preserving (see ADR-0026). The real fix (push ranking into the DB query, or cap the fetch much closer to `feed_size`) is a separate, larger change.
- `auth.LoginCommand`'s blocking call is not fixed in this lab.
- py-spy flamegraph capture requires interactive `sudo` on macOS, which wasn't available non-interactively while producing this audit — `time.process_time()` instrumentation was used instead and is documented as such, not hidden. `make profile` works for anyone re-running this with sudo access.
- `libs/matching-core` is not yet covered by `mutmut`.
- Frontend accessibility/SEO findings above are recorded, not fixed.
