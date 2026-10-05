# Redis pub/sub as the cross-slice event bus

- Status: accepted (implementation currently scoped out — see `ai/audit.md` Part A #2–3)
- Date: 2026-10-02

## Context

`notifications` needs to react to things `matching` and `chat` do (a new match, a new message) without importing either slice's service — that would violate the ADR-0002 boundary rule. Some decoupled signaling mechanism is needed between slices that don't know about each other.

## Decision

A Redis pub/sub channel is the event bus: `matching` publishes `match.created`, `chat` publishes `message.sent`, `notifications` subscribes to both. This is also reused as a 10-minute-TTL cache for `matching`'s ranked candidate lists, since both uses justify the same dependency.

## Alternatives considered

A direct in-process callback/event-emitter (no Redis) was considered — it preserves the decoupling with less infrastructure, at the cost of not surviving a process restart or scaling past one instance. A full task queue (Celery) was rejected as solving a problem (background job processing) this project doesn't have — pub/sub alone is enough for "notify another part of the process something happened."

## Consequences

Introduces a real infrastructure dependency (Redis) and two things that must stay up for the app to behave correctly: the pub/sub channel and the cache. The MVP's initial implementation deliberately does not build this yet (see `ai/audit.md` Part A #2–3) — `matching`/`chat` currently push directly over the shared WS registry instead, and `matching` queries Postgres directly with no cache. This ADR stays "accepted" because the *decision* (event bus is the right mechanism once the project needs persisted/offline notifications or multi-instance scaling) is still correct; only the timing of building it changed.
