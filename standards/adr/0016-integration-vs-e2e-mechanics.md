# Integration tests use in-process ASGI + real DB; E2E uses a real running server

- Status: accepted
- Date: 2026-10-08

## Context

The brief requires integration tests to run "with dependencies raised: DB, HTTP server" and separately requires E2E (ADR-0016: black-box, full cross-slice journeys). Both tiers touch a real database and a real HTTP surface, so the two need a mechanical distinction beyond scope alone, or "integration" and "E2E" become indistinguishable in practice.

## Decision

Integration tests exercise one endpoint/slice at a time via `httpx` against the FastAPI app object directly (`ASGITransport`, in-process — no separate server process, no real TCP socket) with a real `testcontainers` Postgres+PostGIS underneath (per `standards/DEFINITION_OF_DONE.md`'s existing integration-test line). E2E tests run the app as an actual separate process — `docker compose` bringing up the backend container plus real Postgres — and drive it over genuine HTTP/WS from outside the process, the way an external client would.

## Alternatives considered

Running both tiers the same way (always a real separate server process + docker compose), differing only in how many endpoints a given test chains, was the simpler alternative — one test-infrastructure setup instead of two. Rejected: it makes every single-endpoint integration test pay the cost (startup time, container orchestration) of a full E2E test for no benefit, and it stops being able to catch the class of bug E2E is uniquely positioned for — a container-networking, startup-config, or environment-variable-wiring problem — since integration tests would never actually run the app as a deployed process at all.

## Consequences

Two distinct pieces of test infrastructure to maintain instead of one: `testcontainers`-backed fixtures for integration tests, and a `docker compose`-based harness for E2E. Integration tests stay fast enough to run routinely (CI on every PR, per the existing DoD); E2E tests are slower and heavier, closer to the cost profile that justifies the mutation-testing-stays-manual decision (ADR-0018) rather than running on every push. The real payoff: E2E is the only tier that would catch e.g. a missing environment variable in the Railway deploy config or a Docker networking misconfiguration, which in-process ASGI tests structurally cannot.
