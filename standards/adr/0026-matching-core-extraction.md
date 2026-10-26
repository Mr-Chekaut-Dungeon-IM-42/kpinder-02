# Extracting matching-core as a ports-based library

- Status: accepted
- Date: 2026-10-26

## Context

Lab 5's load test (50k seeded users, Locust weighted mixed journey, local
docker-compose — see `ai/audit/lab-5.md`) identified `matching.GetFeedQuery`
as the one endpoint whose own design doesn't scale, independent of DB tuning:

- Uncontended: ~30ms wall per request.
- At 150 concurrent requests: p50 430-520ms, p95 900-1100ms, p99 1500-1900ms
  — a 15-20x blowup.
- Bumping the SQLAlchemy connection pool 10x (5+10 → 50+100) made no
  measurable difference, ruling out pool exhaustion.
- Direct in-process `time.process_time()` instrumentation showed the
  candidate query decodes up to 500 full `User` ORM rows per request at
  ~10-18ms of real CPU time — synchronous, on the single uvicorn event-loop
  thread. At 150 concurrent requests that's ~1.5-2.7s of CPU demand against
  what is effectively one core, which matches the observed queueing collapse.

This is a real, root-caused bottleneck in one module's *design* (fetch far
more rows than are ever used, decode all of them, discard all but the top
20), not a missing index or a tunable. It was also the richest candidate for
this lab's extraction exercise: a repository query + a scoring algorithm +
a DI boundary, cleanly separable from the rest of the `matching` slice
(swipe/match creation stays where it is).

ADR-0019 already introduced constructor-injected infrastructure (commands/
queries take `db: AsyncSession`, `storage: PhotoStorage` directly). That
solved parameter drilling and patch-free unit testing, but it did not make
the *business logic itself* infra-agnostic — `GetFeedQuery` still imports
SQLAlchemy and raises `fastapi.HTTPException` directly. A unit test for the
ranking algorithm still has to construct (or mock) a `User` ORM instance and
monkey-patch `app.matching.queries.repository.*` module attributes, exactly
the brittleness ADR-0019 was meant to end for commands/queries' *own* tests
— it just didn't reach one level deeper, into what those classes call.

## Decision

Extract the candidate-selection/ranking logic into `libs/matching-core/`, a
separate `uv`/hatchling package with **zero SQLAlchemy, asyncpg,
geoalchemy2, or FastAPI imports anywhere in its source** (enforced by eye —
`grep -rn "sqlalchemy\|fastapi\|asyncpg\|geoalchemy" libs/matching-core/src/`
should only ever match comments). It depends on its own `Protocol`s, defined
in `matching_core/ports.py`:

```python
class CandidateRepository(Protocol):
    async def get_caller(self, caller_id: str) -> CallerProfile | None: ...
    async def get_candidates(
        self, caller: CallerProfile, radius_km: float, limit: int
    ) -> list[CandidateProfile]: ...

class PhotoUrlResolver(Protocol):
    async def resolve(self, photo_key: str) -> str | None: ...
```

`FeedService` (the extracted `GetFeedQuery`) takes these ports via its
constructor and knows nothing else about where candidates come from. It
raises its own typed errors (`CallerNotFoundError`, `LocationRequiredError`)
instead of `HTTPException` — a library has no business importing a web
framework.

The backend app (`app/matching/adapters.py`) implements both ports against
its real SQLAlchemy repository and R2-backed photo storage.
`app/matching/queries.py`'s `GetFeedQuery` is now a ~40-line adapter: wire
`FeedService`, call it, translate its two typed errors to the two HTTP
statuses the API contract already promised (404/422), map `FeedCandidate` →
`CandidateResponse`. It is pure wiring — "the base module doesn't know about
implementations" means, concretely, that `matching_core` never imports
`app.*` at all, and `app/matching/adapters.py` is the *only* file in the
slice that imports both `matching_core` and SQLAlchemy.

This is a behavior-preserving move, not a fix, for the thing the extraction
was actually scoped to: the 500-row fetch limit, the `ORDER BY User.id`
candidate ordering, and the Jaccard ranking are unchanged. The point of
this lab was to localize and protect the bottleneck behind a clean,
independently-testable boundary — not to redesign the ranking algorithm,
which is a separate, larger change (see Known gaps). One smaller thing in
the same module *was* fixed during the move, not just carried over: photo
URL resolution for the returned candidates was sequential (N candidates
with photos = N awaited round-trips, one after another); `FeedService`
resolves them concurrently via `asyncio.gather` instead, with a regression
test (`test_photo_urls_are_resolved_concurrently`) that proves the
concurrency rather than just the output (see `ai/audit/lab-5.md`'s
"secondary finding"). This was in scope because it lived in the exact code
being moved, unlike the fetch-limit/ranking question above.

## Alternatives considered

- **Leave it in `app/matching/queries.py`, just split into smaller
  functions.** Doesn't satisfy "the base module doesn't know about
  implementations" — any refactor that still imports SQLAlchemy from the
  scoring code can't be unit-tested without a DB-shaped mock, and can't be
  reused outside this FastAPI app.
- **Move the whole `matching` slice into `libs/`.** Rejected: `SwipeCommand`
  and match creation are tightly coupled to this app's transaction/
  unique-constraint-retry idiom (ADR-0009) and aren't part of the measured
  bottleneck — moving them too would be scope creep without a data-backed
  reason.
- **Keep `AsyncSession` as the injected dependency type (ADR-0019's
  existing pattern), just document that callers shouldn't rely on it.**
  Rejected: without an abstract port, nothing stops `FeedService` from
  reaching for a SQLAlchemy-specific query method next time someone edits
  it, and its tests still need a DB-shaped mock. A `Protocol` the library
  itself owns is what actually makes the boundary enforceable, not just
  documented.
- **Push the whole query (filter + rank + limit) into the database query**
  instead of fetching 500 rows to score in Python. This is the real fix for
  the root cause and is recorded as a known gap below — but it changes the
  ranking's actual behavior (e.g. a SQL-side approximation of Jaccard, or a
  materialized interest-overlap column) and deserves its own ADR once
  someone signs up to do it, not folded into an extraction that was scoped
  to be behavior-preserving.

## Consequences

- `libs/matching-core` has its own unit test suite
  (`libs/matching-core/tests/`) using in-memory fakes for both ports — no
  Postgres, no FastAPI, no mocking of SQLAlchemy internals. Full branch
  coverage of the ranking/truncation/photo-resolution logic.
- `app/matching/tests/test_feed_adapter.py` covers only the adapter glue
  (error translation, schema mapping) that's left in the app.
- `backend/pyproject.toml`'s `[tool.mutmut]` config no longer targets
  `app/matching/queries.py`'s feed logic (it's not there anymore) —
  mutation testing of the extracted ranking logic is a documented gap, not
  yet run against `libs/matching-core` (see `ai/audit/lab-5.md`).
- The backend depends on `matching-core` as a local editable path
  dependency (`[tool.uv.sources]` in `backend/pyproject.toml`). It is not
  published anywhere — "library" here means "a separately versioned,
  separately testable package with its own boundary," not "on PyPI."
- The feed endpoint's actual latency under load is **unchanged** by this
  ADR — see "Known gaps" and the top-3 in `ai/audit/lab-5.md` for what
  would actually fix it.
- **Docker build context changed**: `backend/Dockerfile` previously built
  from `backend/` as its own self-contained context. `matching-core` is a
  local uv path dependency one level up (`../libs/matching-core` relative
  to `backend/pyproject.toml`), so the Dockerfile now needs the **repo
  root** as its build context to see `libs/`. `docker-compose.yml`'s
  `backend` service and the repo-root `railway.json` (moved from
  `backend/railway.json`) were updated accordingly. This requires a
  one-time manual change in Railway's dashboard — the backend service's
  **Root Directory** setting goes from `backend` to the repo root (`/`) —
  the same category of "can't be expressed as a file in this repo" change
  lab-4's branch protection setting was (`DEFENSE.md`).

## Known gaps

- The 500-row over-fetch and arbitrary `ORDER BY User.id` candidate
  ordering are the real root cause of the latency blowup and are not fixed
  here (see "Alternatives considered" above). This ADR protects the
  bottleneck behind a boundary that makes it independently testable and
  benchmarkable; it does not resolve it.
- `libs/matching-core` isn't yet covered by `mutmut` — it's a separate
  package with its own `pyproject.toml`, and wiring mutation testing across
  a package boundary wasn't attempted this lab.
