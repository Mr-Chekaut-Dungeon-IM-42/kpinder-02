# WebSocket test tooling: Starlette TestClient for integration, `websockets` for E2E

- Status: accepted
- Date: 2026-10-08

## Context

`chat`'s live-push behavior (spec.md §3: new/edited/deleted message pushed over the shared WS registry) is a real, spec'd behavior that needs coverage at more than one tier, but `httpx` (the integration tier's HTTP client, ADR-0017) has no WebSocket support at all — a different client is needed for the WS half of these scenarios, at each tier.

## Decision

Integration tests use Starlette/FastAPI's built-in `TestClient.websocket_connect` — in-process, pairing naturally with the in-process ASGI-transport mechanics already chosen for that tier (ADR-0017) — to assert that a REST call (send/edit/delete) results in a push once committed. E2E tests use the real `websockets` client library, connecting over an actual TCP socket to the dockerized server (ADR-0017's E2E harness), to verify the full stack — real network, real shared connection registry, real process boundary — actually delivers the push end-to-end.

## Alternatives considered

Skipping WS testing entirely and covering only the REST side (message rows created/edited/deleted correctly) was the lower-effort option. Rejected: "push the update live to the other side if connected" is an explicit, named behavior in spec.md §3, not an implementation detail — leaving it completely unverified at every tier is exactly the kind of gap this lab's audit step (top-3 places green tests don't catch real bugs) is designed to surface, so deliberately not testing it here would be choosing to fail that part of the lab rather than defer it.

## Consequences

Two different WS client APIs are used across tiers (`TestClient.websocket_connect`'s context-manager style vs. `websockets`' async connection), which is slightly more to learn than a single library end-to-end — but each is the natural fit for its tier's transport (in-process ASGI vs. a real socket), consistent with ADR-0017's reasoning: integration and E2E are mechanically different environments, not just different scopes, and their respective WS tooling should reflect that rather than force one library to do both jobs.
