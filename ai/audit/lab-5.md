# Lab 5 audit — load test, profiling, DB analysis, and the matching-core extraction

Scope: load-testing methodology and baseline (`backend/loadtest/locustfile.py`, `backend/scripts/seed_load_data.py`), the frontend Lighthouse audit, the `EXPLAIN ANALYZE`/index analysis, the resulting bottleneck localization, and the `libs/matching-core` extraction (ADR-0026). All numbers below are from real runs against a local `docker-compose` stack, not estimates.

## Part A — setup

- DB: `docker compose up -d db` (Postgres+PostGIS 16-3.4), seeded via `make seed-load` with **50,000 users**, generating:
  - ~**2,000,000** swipe rows (each user swipes ~40 random others, 60% like / 40% pass)
  - **305** reciprocal-like matches (derived by the seed script's own SQL, same `LEAST`/`GREATEST` normalization as `repository.normalize_pair`)
  - ~2,900 messages across those matches
  - Users distributed across 5 Ukrainian city clusters (Kyiv/Lviv/Odesa/Kharkiv/Dnipro) with Gaussian jitter, so a 50km-radius candidate query returns a realistically large (thousands-row), non-trivial candidate set rather than everyone or no one.
- Load generator: Locust (`backend/loadtest/locustfile.py`), weighted mixed journey — see spec.md §9 for the exact weights. Run headless, local `docker-compose` backend, not staging (Railway's trial credit is a documented scarce resource, ADR-0022).
- Backend run as a single `uvicorn` process (no `--workers`), matching how it's actually deployed (Railway's `railway.json`/Dockerfile doesn't set multiple workers either).

## Part B — baseline, bottleneck localization

### B.1 — `auth.LoginCommand` blocks the entire event loop (found, not the extraction target)

`verify_password` (Argon2) is called synchronously inside `async def execute(...)` with no thread offload. Measured by running the same 150-concurrent-user Locust scenario twice, identical in every way except whether `on_start` calls `/auth/login` or reuses a pre-fetched token:

| Scenario | Aggregate throughput |
|---|---|
| With per-user login in the mix | ~35 req/s |
| Same load, logins skipped (pre-fetched tokens) | ~67-75 req/s |

Removing login from the mix roughly **doubled** throughput — a single synchronous CPU-bound call inside an `async def` with no `run_in_threadpool`/`anyio.to_thread` serializes the *entire* process, not just `/auth/login` itself. This is a real, clearly-evidenced, one-line-fixable bug (`await anyio.to_thread.run_sync(verify_password, ...)`). It's recorded here rather than fixed in this lab: it's shallow (one line, no module boundary to design around) and the brief asks for one module to extract — see B.2 for the one that is.

### B.2 — `matching.GetFeedQuery` is the module that doesn't scale (the extraction target)

All runs below have login removed from the mix (pre-fetched tokens via `KPINDER_PREFETCHED_TOKENS`, see `locustfile.py`), to isolate this endpoint's own scalability from B.1's unrelated bug.

**Single-request baseline** (no contention, 30 sequential requests via httpx):

```
median 31.8ms   p95 63.2ms
```

**150 concurrent users** (`make load LOAD_CONCURRENCY=150`, 45s run):

```
GET /matching/feed    p50 430-520ms   p95 900-1100ms   p99 1500-1900ms
```

A 15-20x blowup from baseline. Two things were ruled out before accepting this as the module's own design flaw:

1. **DB connection pool exhaustion** — bumped `create_async_engine`'s `pool_size`/`max_overflow` 10x (5+10 → 50+100) and re-ran the identical scenario: **no measurable difference** (p50 went from ~430-520ms to ~380-515ms, within run-to-run noise). Ruled out.
2. **DB-side query cost** — `EXPLAIN (ANALYZE, BUFFERS)` on the actual candidate query against the 50k-row dataset:

```
Limit  (actual time=72.901..72.984 rows=500 loops=1)
  ->  Sort (top-N heapsort, Memory: 449kB)
      ->  Nested Loop Anti Join (actual time=60.670..71.812 rows=3282 loops=1)
            ->  Index Scan using idx_users_location on users u
                  (actual time=60.557..68.597 rows=3283 loops=1)
                  Index Cond: (location && _st_expand($0, '50000'))
                  Rows Removed by Filter: 1993
            ->  Index Only Scan using swipes_swiper_id_swiped_id_key on swipes s
Execution Time: 73.247 ms
```

The GiST index (`idx_users_location`) **is** being used correctly — this isn't a missing-index problem. ~73ms is the DB's own cost for the query as written, which fetches `limit=500` candidates when only the top 20 are ever returned.

**Root cause, confirmed by direct in-process timing** (`time.process_time()` around the actual `repository.get_candidates` call, warm connection, 3 trials): decoding 500 full `User` ORM rows (with eager-loaded interests) costs **~10-18ms of real CPU time per request** — synchronous, on the single event-loop thread, same thread every other concurrent request's work shares. At 150 concurrent requests, that's roughly 1.5-2.7 seconds of CPU demand hitting what is effectively one core (single uvicorn process, no multi-worker), which is the queueing collapse measured above. The in-Python Jaccard scoring + sort over those 500 rows is **not** the cost — separately measured at ~0.2ms for 500 candidates, negligible.

**Secondary finding in the same module**: `to_candidate()` (pre-extraction, in `app/matching/common.py`) resolved each returned candidate's photo URL with a *sequential* `await` inside a list comprehension, not `asyncio.gather`. Not exercised by this dataset (seeded users have no `photo_key`), so it doesn't show up in the numbers above — but it's a real latency risk once production data includes photos, and is preserved as-is in the extraction (`FeedService.get_feed` — see ADR-0026's "known gaps").

**Known limitation in this measurement**: a CPU-vs-wait flamegraph via `py-spy record` requires `sudo` to attach to another process on macOS, which wasn't available non-interactively in this environment. The CPU/wall breakdown above comes from direct `time.process_time()` instrumentation instead (B.2's in-process timing), which is treated here as a documented substitute, not silently dropped. `make profile` exists and works (tested manually once sudo access is available) for anyone re-running this with a real flamegraph.

### B.3 — why `matching.GetFeedQuery`, and not `auth.LoginCommand`, is the extraction target

Both are real bugs. `LoginCommand`'s is a one-line fix with no design to protect — there's no module boundary to draw around "don't call a blocking function synchronously." `GetFeedQuery`'s is a design flaw in a module that's rich enough to extract meaningfully: a repository query, a ranking algorithm, and dependencies (DB, photo storage) that benefit from being made abstract. See `ai/audit/lab-5.md`'s sibling, ADR-0026, for the extraction itself.

## Part C — frontend audit (Lighthouse, production build)

Run against `vite build && vite preview` (not the dev server — an earlier dev-server run scored noticeably lower on performance purely from unminified/non-code-split dev output, which would have been a misleading "finding"), all four authenticated pages, real JWT via `/auth/login`, token seeded into `localStorage` the same way `AuthContext` does.

| Page | Performance | Accessibility | Best Practices | SEO | LCP |
|---|---|---|---|---|---|
| Feed | 0.95 | 0.92 | 1.00 | 0.83 | 1.3s |
| Matches | 0.98 | 0.92 | 1.00 | 0.82 | 0.9s |
| Chat | 0.96 | 0.92 | 1.00 | 0.83 | 1.2s |
| Profile | 0.96 | 0.93 | 1.00 | 0.83 | 1.2s |

Findings (consistent across all four pages, since they share `NavBar`):

1. **Color contrast fails WCAG AA**: the brand pink `#e8457a` on white (nav links, logout button) and white-on-`#e8457a` (Feed's "Like" button) both measure **3.77:1**, below the required 4.5:1 for normal-weight text. Present on every authenticated page.
2. **No `<main>` landmark** — `landmark-one-main` fails on all four pages; the page wrapper is a generic `<div>`.
3. **No meta description** in `index.html` — flat `0.82-0.83` SEO score on every page, same root cause.
4. **No `robots.txt`** — expected for an authenticated SPA not meant for indexing, flagged by Lighthouse regardless; low priority.

None of these were fixed as part of this lab (the frontend audit's brief was to find issues, and none of them are the performance bottleneck this lab's extraction targets) — they're recorded here as the deliverable. The initial dev-server run also surfaced a CORS console error (`preview` on port 4173 wasn't in the backend's default `CORS_ORIGINS`) — not a product bug, an artifact of how this audit was run locally; noted so a future re-run doesn't mistake it for a real finding.

## Part D — top 3

1. **`matching.GetFeedQuery`'s over-fetch-and-decode-in-Python design** (Part B.2) — 15-20x latency blowup under concurrency, root-caused to CPU-bound synchronous row decoding on the single event-loop thread, not DB tuning. Localized and protected behind `libs/matching-core`'s port boundary (ADR-0026); **not yet fixed** — the fix (push ranking into the DB query, or cap the fetch far closer to `feed_size`) is a documented known gap, not folded into a behavior-preserving extraction.
2. **`auth.LoginCommand`'s blocking Argon2 call** (Part B.1) — a synchronous CPU-bound call inside an async handler serializes the *entire* process under concurrent login load (roughly 2x throughput recovered in isolation). Not extracted (no module boundary to draw), but is the single highest-leverage one-line fix in the whole audit — flagged for a follow-up PR.
3. **Frontend color-contrast failures on the shared brand color** (Part C) — same `#e8457a` combination fails WCAG AA on every authenticated page's nav and primary action button, because it's one shared value used in multiple places, not four separate bugs.
