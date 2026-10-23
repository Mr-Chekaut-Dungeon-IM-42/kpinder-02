# Hostname-based service isolation over port shifting

- Status: accepted
- Date: 2026-10-15

## Context

In the initial development environment, developers running a local PostgreSQL instance on standard port `5432` experienced port collisions when starting Docker Compose. To bypass the collision, the team mapped the container to host port `5433` (`ports: ["5433:5432"]`) and hardcoded `localhost:5433` into `.env.example`, `Makefile`, and integration test fixtures. Furthermore, test database detection relied on probing `localhost:5433`.

During the Lab-3 project defense, the teacher critiqued this port-shifting anti-pattern:
> *"from defence: use different hosts, not different ports for testing"*

### Why Port Shifting is an Anti-Pattern
1. **Ports define protocols, hostnames define identity**: Port `5432` is the IANA standard for PostgreSQL (just as `80`/`443` is for HTTP/HTTPS). In production, Kubernetes, and cloud VPCs, database services are never arbitrarily shifted to `5433` or `5434` to prevent overlap; they listen on port `5432` and are distinguished by distinct **hostnames** (e.g. `db`, `db-test`, `postgres.prod.internal`).
2. **Configuration drift and fragility**: Hardcoding port `5433` into application configs and test fixtures breaks environment parity between local development, CI/CD pipelines, Docker networks, and staging environments.
3. **Multi-tenant / CI collision**: If multiple pipelines or developers use hardcoded port numbers, they collide immediately.

## Decision

Completely eliminate port shifting (`5433`) and enforce the standard PostgreSQL port **`5432`** across all environments. Isolate services and testing environments through **hostnames** and **Docker network DNS**:

1. **Standard Port 5432 Everywhere**:
   - `docker-compose.yml` binds PostgreSQL to standard port `"${DB_PORT:-5432}:5432"`.
   - `.env.example`, `backend/.env`, and `Makefile` standardize `DATABASE_URL` on port `5432`.
   - Port `5433` is eradicated from all active application and configuration files.

2. **Hostname Resolution by Environment**:
   - **Inside Docker Compose Network**: Services communicate using Docker embedded DNS service names on port 5432:
     - Development database: `postgresql+asyncpg://kpinder:kpinder@db:5432/kpinder`
     - Test database container: `postgresql+asyncpg://kpinder:kpinder@db-test:5432/kpinder_test`
   - **On Host Machine (Local Terminal / IDE)**:
     - Connects via `localhost:5432`.
     - If the host machine has an existing PostgreSQL server running on `127.0.0.1:5432`, developers can bind Compose to a loopback IP alias (e.g. `127.0.0.2:5432` as `db.kpinder.local` via `/etc/hosts`) without altering the port number.

3. **Dynamic Hostname Integration Test Fixtures**:
   - Integration test suites ([`backend/app/*/tests/test_integration.py`](../../backend/app/auth/tests/test_integration.py)) resolve target hostnames dynamically:
     ```python
     test_host = os.getenv("TEST_DB_HOST", os.getenv("DB_HOST", "localhost"))
     test_port = int(os.getenv("TEST_DB_PORT", "5432"))
     ```
   - If a database is reachable on `test_host:test_port`, tests use it; otherwise, they automatically spin up an ephemeral `Testcontainers` PostGIS instance without manual intervention.

## Alternatives considered

- **Retaining port shifting (5433 for dev, 5434 for tests)**:
  Rejected. Direct violation of course requirements and industry best practices.
- **Pure containerized testing (Option 1)**:
  All tests run inside Docker containers using internal hostnames `db:5432` and `db-test:5432`, with zero host ports exposed.
  *Rejected as sole workflow*: While architecturally pure, running all tests via `docker compose run` degrades developer experience by introducing 3–5s startup latency per test run and making IDE breakpoint debugging difficult.
- **Pure dynamic Testcontainers without local Compose detection**:
  *Rejected as sole workflow*: Spinning up a fresh container on every test run adds ~40s overhead compared to ~1s when testing against an active database container.

## Consequences

- **100% compliance with defense feedback**: Tests and development environments are separated by hostnames (`db`, `db-test`, `localhost`), while preserving standard port 5432.
- **Environment parity**: Connection URLs in Docker, CI, and local host share the same standard port and protocol conventions.
- **Fast developer feedback**: Host tests run against local Compose on standard port 5432 in ~1s, with seamless fallback to Testcontainers when no database is running.
