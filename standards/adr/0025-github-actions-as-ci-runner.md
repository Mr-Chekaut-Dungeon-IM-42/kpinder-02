# GitHub Actions as the CI runner

- Status: accepted
- Date: 2026-10-16

## Context

The repo is hosted on GitHub (`Mr-Chekaut-Dungeon-IM-42/kpinder-02`), and the task requires CI that gates merge via GitHub's own branch-protection required-status-checks mechanism. Branch protection's "required status checks" integrates natively with check runs reported by whatever CI posts them back to a commit/PR — GitHub Actions does this with zero extra configuration.

## Decision

CI runs on GitHub Actions (`.github/workflows/`). Jobs: lint/format (ruff; eslint+prettier), build (backend `uv build`; frontend `vite build`), backend unit tests (blocking), backend integration tests against a `postgis/postgis` service container (blocking), backend e2e tests (advisory, non-blocking), and a PR-title Conventional Commits check (ADR-0024) — all required except e2e, enforced via branch protection on `main`.

## Alternatives considered

- **External CI (CircleCI, Travis, GitLab CI mirrored to GitHub, etc.)**: would need a separate account, its own webhook/app installed on the GitHub repo to report check statuses back for branch protection to see, and in most cases a paid plan for anything beyond a small free allowance. Rejected: it adds an external dependency and an extra integration step to get required-status-checks working, for no capability GitHub Actions lacks here — free minutes are sufficient at this project's scale, and Actions's `services:` block directly supports the Postgres+PostGIS container the integration suite needs.

## Consequences

- CI logic lives entirely in `.github/workflows/*.yml`, versioned alongside the code it tests — no external dashboard to keep in sync with the repo.
- The team is bound to GitHub Actions' free-minutes allowance for public/private repos under the course's GitHub plan; if that ever becomes a constraint, revisiting this ADR is the place to reconsider, not silently adding a second CI system alongside it.
