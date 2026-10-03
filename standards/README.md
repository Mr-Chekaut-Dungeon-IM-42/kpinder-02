# Standards

Engineering standards for this project, established in Lab 1 and binding for the rest of the course.

## Contents

- [`adr/`](adr/) — Architecture Decision Records, [MADR](https://adr.github.io/madr/) format, one file per genuinely contested decision.
- [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md) — what "done" means for a PR before it merges.
- [`CHECKLIST.md`](CHECKLIST.md) — the literal steps to run before opening a PR.

## ADR format (MADR)

Each ADR in `adr/` follows the same shape:

```markdown
# <short title of the decision>

- Status: accepted | superseded by ADR-000X
- Date: YYYY-MM-DD

## Context

What problem forced this decision; what constraints applied.

## Decision

What we chose.

## Alternatives considered

What else was on the table, and why it lost.

## Consequences

What this makes easier, what it makes harder, what it leaves open.
```

ADRs are written only for decisions with a real, defensible tradeoff — not for every technical pick. Routine stack choices (FastAPI, ruff, Vite) are covered by a short blurb in [`spec.md`](../spec.md) instead; see `spec.md` §6 for which decisions warranted an ADR and why.

## Relationship to `spec.md` and `ai/audit.md`

`spec.md` describes the target architecture in full — the ideal design, including pieces (like the Redis event bus) that the team later chose not to build yet for the MVP. [`ai/audit.md`](../ai/audit.md) is where that gap is tracked: it lists what was deliberately scoped out of the initial implementation and why. An ADR can be "accepted" as the right long-term decision while its implementation is still scoped out — the ADR records the *decision*, `ai/audit.md` records the *current build status* against that decision.
