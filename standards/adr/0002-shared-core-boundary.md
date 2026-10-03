# Shared/core module as the only cross-slice dependency

- Status: accepted
- Date: 2026-10-02

## Context

ADR-0001 commits to vertical slices, but slices aren't actually independent: `matching` needs the `User`/`Profile`/`Interest` data that `auth` manages; `chat` needs to know who's matched (from `matching`). Some mechanism has to let slices share data without collapsing back into one undifferentiated module.

## Decision

A `shared/` (core) module — not itself a slice — holds: the DB session factory, the JWT-verify dependency (identifies the current user for any slice's router), the WebSocket connection registry, and the core data models (`User`, `Profile`, `Interest`, `UserInterest`). Any slice's repository may read `shared`'s tables directly. The rule is: slices may depend on `shared`, never on each other's router or service.

## Alternatives considered

Letting `matching` import `auth`'s service to fetch profile data was rejected — it would mean an N-service-call pattern for a ranking query that needs one SQL statement with filters, and it reintroduces the exact coupling vertical slices exist to avoid. A full microservice split (separate databases per slice) was never seriously on the table for an MVP of this size.

## Consequences

Reading a shared table directly from a slice's own repository is normal and doesn't violate the no-cross-slice-import rule — the rule is about not calling another slice's *business logic*, not about never touching its data. This distinction has to stay crisp or the whole slice boundary erodes by exception.
