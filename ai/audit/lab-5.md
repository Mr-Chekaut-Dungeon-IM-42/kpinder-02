# Lab 5 audit — load test, profiling, DB analysis, optimizations, and the matching-core extraction

Scope: load-testing methodology and baseline (`backend/loadtest/locustfile.py`, `backend/scripts/seed_load_data.py`), the frontend Lighthouse audit, the `EXPLAIN ANALYZE`/index analysis, the resulting bottleneck localization, the `libs/matching-core` extraction (ADR-0026), and empirical verification of applied fixes. All numbers below are from real runs against a local `docker-compose` stack, not estimates.

## Part A — setup

- DB: `docker compose up -d db` (Postgres+PostGIS 16-3.4), seeded via `make seed-load` with **50,000 users**, generating:
  - ~**2,000,000** swipe rows (each user swipes ~40 random others, 60% like / 40% pass)
  - **305** reciprocal-like matches (derived by the seed script's own SQL, same `LEAST`/`GREATEST` normalization as `repository.normalize_pair`)
  - ~2,900 messages across those matches
  - Users distributed across 5 Ukrainian city clusters (Kyiv/Lviv/Odesa/Kharkiv/Dnipro) with Gaussian jitter, so a 50km-radius candidate query returns a realistically large (thousands-row), non-trivial candidate set rather than everyone or no one.
- Load generator: Locust (`backend/loadtest/locustfile.py`), weighted mixed journey — see spec.md §9 for the exact weights. Run headless, local `docker-compose` backend, not staging (Railway's trial credit is a documented scarce resource, ADR-0022).
- Backend run as a single `uvicorn` process (no `--workers`), matching how it's actually deployed (Railway's `railway.json`/Dockerfile doesn't set multiple workers either).

---

## Part B — baseline, bottleneck localization & load testing results

### B.1 — Single-request uncontended baseline (1 user)

Sequential httpx requests, no contention, warm connection:
- `GET /matching/feed`: median **31.8ms**, p95 **63.2ms**, p99 **78.0ms**
- `GET /matching/matches`: median **12.0ms**, p95 **22.5ms**
- `POST /matching/swipe`: median **8.5ms**, p95 **18.0ms**

---

### B.2 — 150 concurrent users (BEFORE optimizations)

Initial run with 150 concurrent users (`make load LOAD_CONCURRENCY=150`, 45s run, weighted journey):

| Endpoint / Metric | Baseline (Uncontended) | Under 150 concurrent users (Before fixes) | Degradation |
|---|---|---|---|
| `GET /matching/feed` | p50 31.8ms / p95 63.2ms | **p50 430–520ms / p95 900–1100ms / p99 1500–1900ms** | **15–20x blowup** |
| `GET /matching/matches` | p50 12.0ms / p95 22.5ms | p50 25–40ms / p95 80–120ms | 2–4x blowup |
| Aggregate throughput | N/A | **~35 req/s** (with login) → **~69 req/s** (logins isolated/offloaded) | Stalled |

**Root cause localization:**
1. **Event Loop blockage by Argon2 (found and fixed first):** `verify_password` was called synchronously in an `async def`. Offloaded via `anyio.to_thread.run_sync`, throughput rose from ~35 to ~69 req/s.
2. **`GET /matching/feed` CPU bottleneck:** DB query cost was ~73ms (`EXPLAIN ANALYZE`), but decoding 500 full ORM `User` rows + eager-loaded `interests` (`selectinload`) cost **~10–18ms of real CPU time per request** in the single asyncio event-loop thread. At 150 concurrent requests, this produced 1.5–2.7s of CPU demand, collapsing into a massive queue.
3. **Correlated scalar subquery:** `caller_location = select(User.location).where(User.id == caller.id).scalar_subquery()` executed an avoidable subquery on every request despite `caller.location` already being in memory.
4. **Missing composite index on `matches`:** `WHERE user_a_id = :id OR user_b_id = :id ORDER BY created_at DESC` caused a full Seq Scan for `user_b_id` due to B-tree left-prefix rules, followed by an in-memory `Sort (quicksort)`.

---

### B.3 — 150 concurrent users (AFTER optimizations: pool 50, direct geometry, composite indexes)

Re-run with identical parameters: 150 users, spawn-rate 25/s, 45s run-time, clean uvicorn without `--reload`:

```
Type     Name                                        # reqs      # fails |    Avg     Min     Max    Med |   req/s  failures/s
--------|------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
POST     /auth/login                                    150     0(0.00%) |    329     118     587    320 |    3.36        0.00
GET      /chat/[match_id]/messages                        4     0(0.00%) |      6       3       7      7 |    0.09        0.00
POST     /chat/[match_id]/messages (send)                 1     0(0.00%) |     11      11      11     11 |    0.02        0.00
GET      /matching/feed                                2316     0(0.00%) |     37       7     601     19 |   51.85        0.00
GET      /matching/matches                              625     0(0.00%) |     13       1     336      4 |   13.99        0.00
POST     /matching/swipe                                812     0(0.00%) |     17       2     393      7 |   18.18        0.00
--------|------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
         Aggregated                                    3908     0(0.00%) |     40       1     601     16 |   87.50        0.00

Response time percentiles (approximated)
Type     Name                                                50%    66%    75%    80%    90%    95%    98%    99%   100%
--------|----------------------------------------------|--------|------|------|------|------|------|------|------|------
POST     /auth/login                                         320    360    410    420    480    510    540    570    590
GET      /chat/[match_id]/messages                             7      7      8      8      8      8      8      8      8
POST     /chat/[match_id]/messages (send)                     12     12     12     12     12     12     12     12     12
GET      /matching/feed                                       19     23     29     38     58    130    300    380    600
GET      /matching/matches                                     4      6      8      9     23     40    190    240    340
POST     /matching/swipe                                       7     11     15     17     33     51    130    240    390
--------|----------------------------------------------|--------|------|------|------|------|------|------|------|------
         Aggregated                                           16     21     26     33     67    250    360    420    600
```

**Key improvements:**
- `GET /matching/feed` median latency plummeted from **480ms down to 19ms** (**25x speedup** / -96%).
- `GET /matching/feed` p95 dropped from **1000ms down to 130ms** (**~8x speedup**).
- `GET /matching/matches` median latency dropped to **4ms** (B-tree composite index eliminates Seq Scan & Sort).
- Total system throughput increased to **87.50 req/s** (+27% increase over previous state; 2.5x over initial).
- Total requests processed: 3,908 with **0.00% failures**.

---

### B.4 — Saturation & Stress Soak Test (1,000 concurrent users)

To identify the single-process saturation ceiling (the "knee of the curve"), the system was stressed with **1,000 concurrent users** (spawn-rate 100/s, 60s run):

```
Type     Name                                        # reqs      # fails |    Avg     Min     Max    Med |   req/s  failures/s
--------|------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
POST     /auth/login                                    991     1(0.10%) |   6302     202   30156   4700 |   30.76        0.03
GET      /chat/[match_id]/messages                        2     0(0.00%) |  11425     109   22740  22740 |    0.06        0.00
GET      /matching/feed                                1568     0(0.00%) |   5388      78   25203   5600 |   48.67        0.00
GET      /matching/matches                              443     0(0.00%) |   5138      37   25310   5400 |   13.75        0.00
POST     /matching/swipe                                360     0(0.00%) |   4556      59   20203   5300 |   11.17        0.00
--------|------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
         Aggregated                                    3364     1(0.03%) |   5539      37   30156   5400 |  104.42        0.03

Response time percentiles:
Aggregated: 50% = 5400ms, 90% = 14000ms, 95% = 15000ms, 99% = 22000ms, Max = 30156ms.
```

**Engineering analysis:**
1. **Resilience (99.97% success):** 3,363 out of 3,364 requests succeeded without process crash or memory leak.
2. **Physical single-core ceiling:** Throughput saturated at **104.42 req/s**, representing 100% single-thread CPU utilization.
3. **Queueing latency (Little's Law):** With $L = 1000$ and $\lambda \approx 104\text{ req/s}$, average waiting time in the socket backlog queue reaches $W = L / \lambda \approx 9.6\text{s}$ (measured median 5.4s).
4. **Pool timeout root-cause:** Exactly 1 request timed out after `30156ms` due to SQLAlchemy's 30s connection acquisition limit (`QueuePool`) during the initial 100 users/s login storm.

---

### B.5 — Profiler Analysis (`py-spy`: Top Mode & SVG Flamegraph)

Profiling was executed on the live running uvicorn worker process under concurrent Locust load using `py-spy 0.4.2` in both live interactive mode (`py-spy top --idle`) and full sampling record mode (`py-spy record --idle -o kpinder_flame.svg`).

#### B.5.1 — Live Top Mode (`py-spy top --idle`)
```
GIL: 0.00%, Active: 6.00%, Threads: 9

  %Own   %Total  OwnTime  TotalTime  Function (filename)
800.00% 800.00%    2006s     2006s   wait (threading.py)
100.00% 100.00%   107.7s    119.7s   run (asyncio/runners.py)
  0.00%   0.00%   22.69s    22.69s   verify_secret (argon2/low_level.py)
  0.00%   0.00%    1.77s     1.77s   __init__ (sqlalchemy/orm/state.py)
  0.00%   0.00%    1.68s     5.97s   _instance (sqlalchemy/orm/loading.py)
  0.00%   0.00%    1.07s     2.13s   _prepare_and_execute (sqlalchemy/dialects/postgresql/asyncpg.py)
  0.00%   0.00%    1.02s     2.43s   _populate_full (sqlalchemy/orm/loading.py)
  0.00%   0.00%   0.570s    0.760s   get (sqlalchemy/orm/identity.py)
  0.00%   0.00%   0.540s    0.540s   execute (asyncpg/connection.py)
  0.00%   0.00%   0.290s     5.73s   get_feed (matching_core/feed.py)
  0.00%   0.00%   0.280s    10.72s   app (fastapi/routing.py)
```

**Key findings from live profiling:**
1. **Threadpool offload verified:** Process operates 9 threads (1 main asyncio loop + 8 worker threads in AnyIO pool). `verify_secret (argon2)` consumed 22.69s of CPU time, but its `%Own` in the main loop is **0.00%** — Argon2 is completely offloaded and no longer stalls the event loop.
2. **Zero GIL contention:** GIL utilization is **0.00%**, Active CPU is **6.00%**. The process is not compute-locked.
3. **Library efficiency:** The pure ranking computation in `get_feed (matching_core/feed.py)` accounted for only **0.29s** of CPU time across the profile run.

#### B.5.2 — SVG Flamegraph Analysis (`kpinder_flame.svg`)
Sampling parameters: 30s duration, 100 Hz sampling rate, `--idle` enabled, non-blocking mode. Total samples recorded: **36,507**.

- **Stack 1: Worker Threadpool Idle Wait (87.01%, 31,763 samples):**
  `_bootstrap (threading.py) -> run (anyio) -> get (queue.py) -> wait (threading.py:355)`
  The 8 background threads spend ~87% of time parked waiting on the work queue.
- **Stack 2: Background Argon2 Hashing (5.62%, 2,051 samples):**
  `_bootstrap -> run (anyio) -> verify (argon2) -> verify_secret (argon2/low_level.py:197)`
  Runs strictly inside worker threads, physically separate from the event loop tower.
- **Stack 3: Main Asyncio Event Loop (5.47%, 1,997 samples):**
  `run (uvicorn/server.py) -> run (asyncio/runners.py) -> fastapi -> matching_core`
  The entire HTTP processing pipeline in the main thread consumes only **5.47%** of total system time. Within this tower:
  - `get_feed (matching_core/feed.py)`: only **0.18%** (66 samples).
  - `get_candidates (adapters.py)`: only **0.13%** (47 samples).
  - SQLAlchemy ORM instance loading (`instances`, `chunks`, `_instance`): ~**1.5%** (down from >80% prior to reducing the candidate pool).
- **CPU vs Wait (I/O) ratio:**
  - **~94% Wait / Idle:** Waiting on PostgreSQL query results (`asyncpg` socket reads) and thread synchronization.
  - **~6% Active CPU:** Fast serialization, routing, and in-memory scoring.

---

## Part C — Frontend audit (Lighthouse, production build)

Run against `vite build && vite preview` across all 4 authenticated pages:

| Page | Performance | Accessibility | Best Practices | SEO | LCP |
|---|---|---|---|---|---|
| Feed | 0.95 | 0.92 | 1.00 | 0.83 | 1.3s |
| Matches | 0.98 | 0.92 | 1.00 | 0.82 | 0.9s |
| Chat | 0.96 | 0.92 | 1.00 | 0.83 | 1.2s |
| Profile | 0.96 | 0.93 | 1.00 | 0.83 | 1.2s |

**Identified issues:**
1. **WCAG AA contrast failure:** `#e8457a` on white gives a contrast ratio of 3.77:1 (needs $\ge$ 4.5:1).
2. **Landmark absence:** missing `<main>` container on pages (`landmark-one-main`).
3. **SEO & Head metadata:** missing `<meta name="description">` and `robots.txt`.

**Implemented Frontend Fixes:**
- Replaced brand accent color `#e8457a` with WCAG AA compliant `#c2255c` (contrast ratio **5.66:1** against `#ffffff`, well exceeding the 4.5:1 minimum) across all page CSS modules (`NavBar`, `Feed`, `Matches`, `AuthForm`, `Profile`, `Chat`).
- Wrapped all pages (`Feed.tsx`, `Matches.tsx`, `Chat.tsx`, `Profile.tsx`, `Login.tsx`, `Register.tsx`) with semantic `<main className={styles.page}>` landmarks, fixing `landmark-one-main`.
- Added `<meta name="description" content="Kpinder — Smart dating service for KPI students and tech enthusiasts.">`, descriptive title, and theme color `#c2255c` to `frontend/index.html`.
- Added `frontend/public/robots.txt` disallowing crawlers on private web app routes.
- Verified via `npm run lint` and `npm run build` (Vite 8.3.4 clean production bundle).

---

## Part D — 6 Cut Corners & Found Issues (Tracked with Execution Status)

The following 6 concrete architectural and performance issues were audited, localized, and resolved, divided equally between the two team members:

### Студент 1 (Іван Федоренко) — Backend, Concurrency & Algorithms

#### 1. Over-fetching & ORM Decoding in `get_candidates`
- **Issue:** Hardcoded `limit=500` candidates with eager `selectinload(User.interests)` meant 500 ORM objects and thousands of interest tags decoded synchronously on the event loop (~15ms CPU). Also utilized an unnecessary `scalar_subquery` for caller location.
- **Resolution:** Lowered candidate fetch pool from 500 to 50 (`DEFAULT_CANDIDATE_FETCH_LIMIT = 50`), providing a 2.5x buffer for Jaccard ranking without 25x over-fetch penalties. Passed `caller.location` directly into `ST_DWithin`.
- **Status:** **`[FIXED]`** (Feed median latency reduced 25x from 480ms to 19ms).

#### 2. Event Loop Blockage by Argon2 Hashing in `auth`
- **Issue:** `SignupCommand` and `LoginCommand` ran CPU-heavy Argon2 hashing synchronously inside `async def` without threadpool offloading, blocking the single event loop thread and halving system throughput (~35 req/s).
- **Resolution:** Wrapped `hash_password` and `verify_password` with `anyio.to_thread.run_sync`.
- **Status:** **`[FIXED]`** (Throughput restored to ~69 req/s under login load; verified in py-spy flamegraph running isolated on worker threads).

#### 3. Sequential `await` in Photo URL Resolution
- **Issue:** Pre-extraction candidate processing resolved photo presigned URLs sequentially in a loop (`[await storage.get_url(...) for c in candidates]`), adding serial network round-trips.
- **Resolution:** Implemented concurrent resolution in `FeedService` via `asyncio.gather` with a regression test ensuring non-sequential execution.
- **Status:** **`[FIXED]`** (Regression test `test_photo_urls_are_resolved_concurrently` passing).

---

### Студент 2 (Лобан Михайло) — Database, Infra, Frontend & Web-Vitals

#### 4. Missing Composite B-Tree Indexes on `matches` Pagination
- **Issue:** `get_matches_page` filters `WHERE user_a_id = :id OR user_b_id = :id ORDER BY created_at DESC`. The table had only `UNIQUE (user_a_id, user_b_id)`, which violated the B-tree left-prefix rule for `user_b_id`, forcing full Seq Scan and in-memory sort.
- **Resolution:** Added composite indexes `(user_a_id, created_at DESC, id DESC)` and `(user_b_id, created_at DESC, id DESC)`. Generated and applied Alembic migration `fe77c7523aa3`.
- **Status:** **`[FIXED]`** (`GET /matching/matches` median latency dropped to 4ms under 150 vUsers).

#### 5. Docker Monorepo Build Context & Dependency Bloat
- **Issue:** Extracting `libs/matching-core` as a local path dependency broke the Docker build context (which only knew `backend/`), while `uv run` in the container default command re-synced dev dependencies (locust, py-spy) on every start.
- **Resolution:** Moved Docker build context to repo root, updated `docker-compose.yml` and `railway.json`, and added `--no-dev` to container runtime commands.
- **Status:** **`[FIXED]`** (Verified via successful root Docker build and CI test job).

#### 6. Frontend WCAG AA Contrast & Semantic HTML / SEO
- **Issue:** Brand color `#e8457a` failed WCAG AA minimum contrast ratio (3.77:1 vs 4.5:1 requirement). Authenticated pages lacked `<main>` landmark, and `index.html` lacked meta description.
- **Resolution:** Replaced brand accent color with WCAG AA compliant `#c2255c` (contrast 5.66:1), wrapped authenticated page views in semantic `<main>`, and added descriptive meta tags and `robots.txt`.
- **Status:** **`[FIXED]`** (Clean build, WCAG AA compliance verified, `<main>` landmarks added across all pages).
