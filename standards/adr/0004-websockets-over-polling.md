# WebSockets over polling for chat

- Status: accepted
- Date: 2026-10-02

## Context

"Real-time messaging" is one of the three MVP features named explicitly in the project brief. The two realistic transports are polling (client re-fetches on an interval) or a persistent WebSocket connection per user.

## Decision

Chat uses native WebSockets via FastAPI. The connection is authenticated through the shared JWT-verify dependency and registered in the shared WS connection registry (`user_id → connection`), which lives in-process on a single server instance for the MVP.

## Alternatives considered

Polling was the initially proposed option — lower implementation cost, trivial to test with ordinary HTTP integration tests, no connection-lifecycle management. It was rejected: the brief names "real-time messaging" as a specific capability, and polling only satisfies that word at low fidelity. Since the project explicitly wants to demonstrate the harder mechanism, the lower-fidelity option would have been cutting a corner the brief didn't ask to cut.

## Consequences

Requires managing connection lifecycle (registry, reconnects) and makes integration testing chat harder than a plain REST endpoint (needs a WebSocket-aware test client). The connection registry is explicitly single-process for the MVP (see `spec.md` §4, "Scoped out") — horizontal scaling would need the registry backed by something shared across instances, which is exactly what ADR-0003's event bus would provide if built out.
