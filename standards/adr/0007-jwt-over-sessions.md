# JWT over server-side sessions

- Status: accepted
- Date: 2026-10-02

## Context

`auth` needs to identify the current user on every subsequent request across all slices. The two standard options are stateless JWTs or server-side sessions (stored in Postgres or Redis, referenced by a cookie).

## Decision

JWT, issued by `auth` on login and verified via a shared dependency (`shared/`, see ADR-0002) that every other slice's router depends on. A single, reasonably long-lived access token is used for the MVP — no refresh-token rotation.

## Alternatives considered

Server-side sessions were considered but rejected for the MVP: they require a session store (another Postgres table, or Redis — see ADR-0003's note on Redis already being a heavier dependency than the MVP currently builds), and the stateless property of JWT fits a REST + WebSocket API without extra infrastructure.

## Consequences

No server-side revocation mechanism — a leaked token is valid until it expires, and there's no way to force-logout a session. This is accepted as a documented MVP limitation (see `spec.md` §4, "Scoped out": "JWT refresh-token rotation"); a production version would need refresh-token rotation and a revocation list at minimum.
