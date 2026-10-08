# E2E tests are black-box API-level, not browser-based

- Status: accepted
- Date: 2026-10-08

## Context

Lab-3 names E2E as a distinct tier from integration tests. The frontend (README: "planned, not yet scaffolded") doesn't exist, so a browser-driven E2E suite (Playwright/Cypress clicking through screens) has nothing to drive. Something still has to occupy the "E2E" tier, distinct from integration tests, for the lab's "all test levels" bar to be met honestly rather than by relabeling integration tests.

## Decision

E2E means black-box, API-level, full user-journey tests: drive the running backend only through its public HTTP/WS surface (no internal imports, no mocking of any kind), chaining a realistic multi-step journey across slices — signup → login → update profile → swipe both directions → match → send/edit/delete a message — against a fully running app and a real Postgres. The distinguishing property from integration tests (ADR-0017) isn't "uses real dependencies" (both tiers do) — it's *scope*: one cross-slice journey exercising the system the way an external client actually would, versus one endpoint/slice at a time.

## Alternatives considered

Deferring E2E entirely until a frontend exists, and documenting it as a scope cut, was the conservative option. Rejected: the lab explicitly asks for E2E as one of four required tiers, and this project's own backend-only test-coverage stance (spec.md §4: "Frontend tests — backend-only test coverage for this lab") already establishes that "E2E" in this project's vocabulary was never going to mean browser automation — there's no reason to treat *this* lab's E2E requirement any differently than the rest of the project treats frontend-adjacent testing. A real black-box journey test exists today and exercises real cross-slice behavior; there's no honest reason to cut it just because it isn't literally a browser clicking buttons.

## Consequences

"E2E" in this project means something different from the term's most common industry usage (which implies a browser/UI) — this ADR exists specifically so a reader doesn't assume otherwise. If a frontend is scaffolded later, a *true* browser E2E suite would be an addition on top of this, not a replacement for it — the API-level journey tests stay valuable as the fastest way to exercise full cross-slice flows without a browser in the loop at all.
