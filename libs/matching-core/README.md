# matching-core

Extracted from `backend/app/matching` (Lab 5 — see repo-root `standards/adr/0026-matching-core-extraction.md`
and `ai/audit/lab-5.md` for why this module specifically, backed by load-test data).

Candidate selection + Jaccard interest-overlap ranking for Kpinder's feed. This
package owns the business logic only — it has **no SQLAlchemy, no asyncpg, no
FastAPI import**, anywhere. It depends on its own `ports.py` Protocols
(`CandidateRepository`, `PhotoUrlResolver`); the backend app supplies concrete
adapters at wiring time (`app/matching/adapters.py`).

This boundary is what "the base module doesn't know about implementations"
means in practice: you can unit-test `FeedService` with in-memory fakes and
never start a database.
