# Candidate pool reduction and feed query optimization

- Status: accepted
- Date: 2026-10-27
- Amends: [ADR-0026](0026-matching-core-extraction.md)

## Context

[ADR-0026](0026-matching-core-extraction.md) successfully extracted candidate scoring and feed assembly into `libs/matching-core`, decoupling business ranking from database and web frameworks via `CandidateRepository` and `PhotoUrlResolver` protocols.

However, ADR-0026 deliberately restricted its scope to be strictly **behavior-preserving** regarding data access:
1. It maintained a hardcoded candidate pool limit of 500 rows (`DEFAULT_CANDIDATE_FETCH_LIMIT = 500`).
2. It preserved a correlated scalar subquery for caller location (`caller_location = select(User.location)...scalar_subquery()`), executing a redundant database round-trip on every feed request despite caller location already residing in memory.
3. It left the primary performance bottleneck unaddressed in production, documenting in its "Known gaps" and "Alternatives considered" that resolving the 15–20x latency blowup (p50 480ms under 150 concurrent users) would require a future, larger architectural overhaul—such as pushing Jaccard interest ranking entirely into PostgreSQL.

Empirical profiling using Locust and `py-spy` under 150 concurrent users revealed that decoding 500 full `User` ORM rows with eager `selectinload(User.interests)` tags consumed **10–18ms of synchronous CPU time per request** on the single asyncio event-loop thread. At scale, this generated 1.5–2.7s of CPU demand against a single core, causing event-loop starvation and queueing collapse.

## Decision

Partially amend and resolve the known gaps in ADR-0026 by optimizing candidate pool sizing and query execution, without abandoning Python-side ranking or compromising domain isolation:

1. **Reduce the candidate fetch pool by 10x (`500 -> 50`)**:
   - In `libs/matching-core/src/matching_core/feed.py`, set `DEFAULT_CANDIDATE_FETCH_LIMIT = 50`.
   - For a standard feed request returning `feed_size = 20`, fetching 50 spatial candidates provides a 2.5x buffer for Jaccard interest overlap re-ranking.
   - Truncating the candidate pool at the SQL level reduces ORM instantiation, relationship hydration, and garbage collection pressure by **90%** (slashing CPU decoding time from ~15ms to ~1.5ms per request).

2. **Eliminate the caller location scalar subquery**:
   - In `SqlAlchemyCandidateRepository.get_candidates` and `repository.get_candidates`, pass the in-memory caller geometry directly into PostGIS `func.ST_DWithin(User.location, caller.location, radius_km * 1000)` instead of executing an embedded `(SELECT location FROM users WHERE id = :caller_id)` subquery.

3. **Add composite B-tree indexes for cursor pagination**:
   - Under the same 150-user load test, `GET /matching/matches` suffered degradation due to `WHERE user_a_id = :id OR user_b_id = :id ORDER BY created_at DESC`. The table's existing `UNIQUE (user_a_id, user_b_id)` constraint violated B-tree left-prefix rules for `user_b_id`, forcing full Sequential Scans and in-memory quicksorts.
   - Introduce composite B-tree indexes `(user_a_id, created_at DESC, id DESC)` and `(user_b_id, created_at DESC, id DESC)` via Alembic migration `fe77c7523aa3`.

## Why this is a "Partial Fix" to ADR-0026

ADR-0026 contemplated that the "real fix" for candidate ranking would be pushing Jaccard scoring into SQL (e.g., PostgreSQL `intarray` or text search extensions) or maintaining a materialized interest-overlap index.

This ADR demonstrates that a full SQL rewrite is unnecessary to eliminate the bottleneck:
- Profiling via `py-spy` confirmed that in-memory Jaccard ranking in `libs/matching-core/src/matching_core/scoring.py` over 50 items consumes only **0.29s of CPU time (<0.2% of total runtime)** across thousands of requests. The bottleneck was never the math in Python; it was the synchronous ORM hydration of 500 rows on the event loop.
- It is a **partial fix** because:
  - It preserves the two-stage pipeline: PostGIS spatial filtering in SQL -> top 50 candidates -> Jaccard ranking in Python -> top 20 candidates returned.
  - If a user has hundreds of nearby candidates, the top 50 spatial candidates evaluated by Python might not contain the globally highest theoretical Jaccard score found in candidates 51–500. For dating application semantics, prioritizing spatial proximity and recent activity over exhaustive Jaccard scanning across the entire database is an acceptable product trade-off that preserves millisecond response times.

## Alternatives considered

- **Full SQL pushdown (Jaccard in PostgreSQL via extensions or PL/pgSQL)**:
  - Rejected: Coupling interest intersection to SQL complicates the query planner, ties business ranking logic to PostgreSQL-specific functions, and breaks the pure domain boundary established in `libs/matching-core`. Given that Python scoring over 50 items takes <0.5ms, moving this logic to SQL would introduce maintenance complexity with negligible performance gain.
- **Retain 500 candidates and scale horizontally (multiple uvicorn workers)**:
  - Rejected: Masking inefficient algorithmic design by consuming additional CPU cores wastes infrastructure resources and budget on container platforms (such as Railway).
- **Dynamic candidate pool sizing (`feed_size * multiplier`)**:
  - Rejected: Sizing the pool dynamically based on user-supplied query parameters opens an avenue for client-induced event loop degradation (e.g., requesting `feed_size=100` would reintroduce large ORM decoding pauses). A fixed ceiling of 50 guarantees bounded CPU execution time per request.

## Consequences & Empirical Verification

All numbers below were measured under identical test conditions (150 concurrent users, spawn rate 25/s, 45s run, local docker-compose stack without uvicorn `--reload`):

- **Feed latency collapse resolved**:
  - `GET /matching/feed` median latency dropped from **480ms down to 19ms** (a **25x speedup** / 96% reduction).
  - `GET /matching/feed` p95 dropped from **1000ms down to 130ms** (an **8x speedup**).
- **Matches pagination optimized**:
  - `GET /matching/matches` median latency dropped to **4ms**, eliminating sequential scans.
- **Throughput & stability**:
  - System throughput increased from 35–69 req/s up to **87.50 req/s** (+27% to +150% improvement).
  - **0.00% request failure rate** across 3,908 processed requests.
- **Flamegraph verification (`py-spy record`)**:
  - Main event loop execution represents only **5.47%** of total system time; worker thread idle wait accounts for 87%.
  - SQLAlchemy ORM instance decoding dropped from overwhelming the event loop to ~**1.5%** of runtime.
  - Domain ranking in `matching_core/feed.py` takes only **0.18%** of samples.
- **Architecture preserved**:
  - `libs/matching-core` remains completely decoupled from SQLAlchemy, PostGIS, and FastAPI.
  - Full test coverage with in-memory fakes passes in `libs/matching-core/tests/` (12 tests) and backend (82 tests).
