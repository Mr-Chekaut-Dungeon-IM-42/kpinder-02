# No `/auth/logout` endpoint, no JWT revocation (supersedes ADR-0011, restores ADR-0007 as written)

- Status: accepted
- Date: 2026-10-08

## Context

ADR-0011 added a `RevokedToken` blocklist specifically because `/auth/logout` had been listed as a functional requirement, and a no-op logout endpoint was judged indefensible once named as a real requirement. Revisiting it: the only reason that table, its extra per-request lookup, and the insert-and-catch idempotency handling on the logout path existed at all was to make `/auth/logout` mean something. Removing the endpoint removes the reason.

## Decision

Drop `/auth/logout` entirely — it is not part of this project's functional requirements. Drop `RevokedToken` and the JWT-verify dependency's blocklist check. Auth reverts to exactly what ADR-0007 originally specified: a single long-lived, stateless JWT with no server-side revocation mechanism of any kind. "A leaked token is valid until it expires" is restored as an accepted, documented MVP limitation rather than something a later decision patched over.

## Alternatives considered

Keeping `/auth/logout` as a client-side-only no-op (discard the token locally, no server state) was the other option on the table once revocation itself was ruled out. Rejected here in favor of removing the endpoint outright: a no-op endpoint that looks like it does something security-relevant but doesn't is worse than not having it — it invites a frontend (or a reviewer) to assume logging out actually invalidates the token server-side when it never did. If the project later needs "forget me on this device" UX, that's a pure frontend concern (clear the stored token) that needs no backend endpoint at all.

## Consequences

`shared/` loses a table and a per-request DB lookup that existed only to support logout — one less moving part, and the JWT-verify dependency goes back to being a pure signature/expiry check with no DB access at all (cheaper than ADR-0011's version, and simpler than reasoning about `RevokedToken`'s own idempotency/no-cleanup-needed properties). The real cost is exactly what ADR-0007 already named: no way to force-invalidate a stolen or shared-device token before it naturally expires. That's accepted as a scope cut for this MVP, same as the other items in `ai/audit.md` Part A, not solved and then silently removed.
