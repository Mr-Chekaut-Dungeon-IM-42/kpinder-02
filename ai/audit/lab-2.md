## Part A (continued) — Lab-2 functional-requirements scope cuts (2026-10-08)

8. **No email verification on `POST /auth/signup`.** Account is active immediately; no confirmation token/email step.
9. **No password complexity rules beyond a minimum length.** No uppercase/symbol/entropy requirements.
10. **No content moderation on messages.** Only a generous max-length cap; no profanity filter.
11. **No old-photo cleanup on re-upload.** `POST /auth/upload_photo` overwrites `User.photo_url`; the previous R2 object is left orphaned, not deleted.
12. **Once in, there's no way out - logout removed entirely, no JWT revocation.** Originally specified, then built out as a Postgres `RevokedToken` blocklist (ADR-0011), then reverted: a no-op logout (discard the token client-side only) was judged indefensible once named as a real endpoint, so rather than keep a blocklist whose only purpose was to make that endpoint mean something, the endpoint itself was cut and auth reverted to ADR-0007 exactly as originally written (see ADR-0014). A leaked or shared-device token stays valid until natural expiry — an accepted MVP limitation, not an oversight.
13. **No content moderation (no admins and no user bans)**

### Query correctness (N+1 review)

Reviewed every repository query across `auth`, `matching`, `chat` for N+1 shape:
- `auth.get_user_by_id` / `matching.get_user_with_interests`: `selectinload(User.interests)` + `UserInterest.interest` mapped `lazy="joined"` — one query, interests included, no per-row follow-up.
- `matching.get_candidates`: single query, `NOT EXISTS` anti-join against `Swipe` (not a fetch-ids-then-filter-in-Python pass, per spec.md §3.3.1) — correct shape, just missing the `LIMIT`/`ORDER BY` fixed above.
- `matching.get_matches` / `get_users_by_ids`: the "other side" user for every match on a page is resolved with one batched `WHERE id IN (...)` query, not one query per match row.
- Photo URL resolution (`resolve_photo_url` → `storage.get_url`) is called once per candidate/match item, which looks like a per-row loop, but `generate_presigned_url` is local HMAC signing with no network/DB round trip — not a real N+1, just repeated cheap computation.
- `chat.edit_message` / `delete_message` each do one extra `get_match` query purely to compute the WS recipient id for the push, on top of the message lookup already done for the ownership check — two queries instead of one on every edit/delete. Not N+1 (no loop), just a minor avoidable round trip; left as-is, not worth a migration-free micro-optimization in an audit pass.

No instance of "loop in Python, query per iteration" was found anywhere in the three slices.

### Behavior on failures

- **DB down**: `app.main`'s `OperationalError`/`DisconnectionError` handler returns a generic `503` across every router (spec.md §3's documented pattern) — verified this still applies to `chat` and `matching` too, not just the slice it was originally written for.
- **R2/storage down or misconfigured**: `get_photo_storage()` and `R2PhotoStorage.upload`/`get_url` all convert `RuntimeError`/`BotoCoreError`/`ClientError` into `HTTPException(503)` rather than letting them propagate to Starlette's `ServerErrorMiddleware` (which sits outside `CORSMiddleware` — a real bug found and fixed in phase 2, see the `fix(profile)` commit).
- **WebSocket send failure**: `ConnectionManager.send_event` catches any exception per-socket and disconnects just that socket, so one dead connection (among a user's multiple tabs/devices) doesn't break delivery to the others.
- **WebSocket disconnect (client-side)**: `useWebSocket` reconnects on a fixed 3s timer and tears down cleanly on unmount — no leaked sockets, no silent "looks connected but isn't" state.
- **Expired token on an already-open WS connection**: the JWT is only checked once, at connect time (`get_current_user_id_ws`) — a socket opened just before a token expires stays live past that expiry with no re-check. Consistent with ADR-0013's "no revocation, valid until natural expiry" acceptance for REST, just worth naming explicitly as the same tradeoff extending to the one long-lived connection type in this codebase.
- **Concurrent races**: both races the architecture depends on (duplicate-email signup, reciprocal-like match creation) have an integration test forcing the actual DB-level race, not just a unit test asserting the exception-handling code path runs.
