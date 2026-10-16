# mutmut for mutation testing

- Status: accepted
- Date: 2026-10-08

## Context

Lab-3 requires mutation testing against the backend, naming Stryker/PIT/mutmut/cosmic-ray as the menu of tools. Stryker is JS-only and PIT is JVM-only — neither applies to this Python/pytest backend, which narrows the real choice to `mutmut` vs `cosmic-ray`.

## Decision

Use `mutmut`.

## Alternatives considered

`cosmic-ray` is more configurable — pluggable mutation operators, distributed execution support for large codebases. Rejected for this project: it has a materially heavier configuration surface (an explicit session/config file, separate `init`/`exec`/`report` steps) and a smaller community/less current documentation than `mutmut`, for configurability this project's codebase size doesn't need. `mutmut` integrates directly with pytest with near-zero configuration (`mutmut run` against the existing test suite) and produces a surviving-mutant report (`mutmut results`, `mutmut html`) in the shape the lab's DEFENSE.md classification step needs directly.

## Consequences

Mutation runs are scoped to the module(s) chosen for full unit coverage (spec.md's testing-strategy section) rather than the whole backend — `mutmut`'s per-mutant re-run of the full relevant test file(s) is the main cost driver, and scoping keeps a full run's wall-clock time reasonable as the codebase grows. See ADR-0017 for why this isn't a CI-gating step.
