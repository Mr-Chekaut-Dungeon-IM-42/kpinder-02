# AI output audit

Two different things are tracked in this file. Part A is a record of scope the *team* deliberately cut from a fuller design, for traceability (`spec.md` is plan of implementation without cut-corners).

## Part A — Deliberate scope cuts (2026-10-03)

Six things were designed into an earlier iteration of `spec.md` and then dropped by the team to keep the MVP appropriately scoped.

1. **`notifications` slice removed.** No persisted notifications, no delivery to offline users. An offline user simply sees a new match/message next time they open the relevant list. *Replaces:* a dedicated 4th slice with its own `Notification` table and `GET/POST /notifications` endpoints.
2. **Event-driven architecture removed.** No `match.created` / `message.sent` events, no publishers or subscribers. `matching` and `chat` each push directly over the shared WS registry to the other user if connected — nothing is queued or replayed.
3. **Redis dropped entirely** (both roles it was designed for). No candidate-list cache (`candidates:{user_id}`, TTL 10 min was pure performance polish) — `matching` now queries Postgres directly on every request. No pub/sub message broker (see #2) — the whole dependency is gone, not just unused.
4. **`profile` folded into `auth`.** Four slices instead of five — profile management (including photo upload) lives in `auth` rather than as its own bounded context, since unlike `matching`/`chat`/`notifications` it had no independent events or subscribers to justify separate slice status.
5. **Message read receipts removed.** `Message` has no `read_at`; no "message read" WS push. Chat delivers content only, no read-state tracking.
6. **Production environment removed.** One deployed environment (Railway staging, auto-deploy on merge to `main`). No manual-promotion/tagged-release step, no separate prod secrets.

## Part A (continued) — Lab-2 functional-requirements scope cuts (2026-10-08)

8. **No email verification on `POST /auth/signup`.** Account is active immediately; no confirmation token/email step.
9. **No password complexity rules beyond a minimum length.** No uppercase/symbol/entropy requirements.
10. **No content moderation on messages.** Only a generous max-length cap; no profanity filter.
11. **No old-photo cleanup on re-upload.** `POST /auth/upload_photo` overwrites `User.photo_url`; the previous R2 object is left orphaned, not deleted.
12. **Once in, there's no way out - logout removed entirely, no JWT revocation.** Originally specified, then built out as a Postgres `RevokedToken` blocklist (ADR-0011), then reverted: a no-op logout (discard the token client-side only) was judged indefensible once named as a real endpoint, so rather than keep a blocklist whose only purpose was to make that endpoint mean something, the endpoint itself was cut and auth reverted to ADR-0007 exactly as originally written (see ADR-0014). A leaked or shared-device token stays valid until natural expiry — an accepted MVP limitation, not an oversight.
13. **No content moderation (no admins and no user bans)**

## Part B — Implementation audit (scenario walkthrough, 2026-10-12)

Unlike Part A, these are **cut corners**: code that is simpler than, and does less than, what `spec.md`/the ADRs actually committed to — found by auditing the real implementation against those documents, not things the team consciously scoped out ahead of time (that's Part A).

### Cut corners found

1. **`GET /matching/feed`'s candidate query was unbounded — the `limit` parameter was dead code.** spec.md §3.3.1 explicitly promises the feed is "capped at a fixed page size." `matching/repository.py`'s `get_candidates(db, caller, radius_km, limit)` accepted a `limit` argument and never applied it to the query; `get_feed()` called it with `limit=500` expecting the database to cap the result set, but every row matching the radius/gender/seeking/age filters was fetched into Python (with interests eager-loaded) before the Jaccard sort-and-slice. At real scale (a dense city, generous radius) this is unbounded memory and latency — a materially simpler/weaker implementation than the bounded query spec.md describes. **Fixed in this pass**: `.limit()` is now actually applied, with an explicit `.order_by(User.id)` underneath it — `LIMIT` without `ORDER BY` is non-deterministic in Postgres, so the pre-cap needed a stable order to mean anything.
2. **`matching` never pushes a live WebSocket update on match — `chat` does the analogous push, `matching` doesn't at all.** spec.md says this twice: §1 ("`matching` and `chat` are the only slices with anything to push live... each does so directly over the shared WS registry") and §3.3.1 point 2 ("if found, inserts a `MATCH` row... and pushes a live 'match' update directly to both users over the shared WS registry, if connected"). `grep -rn "ws_manager" backend/app/matching/` returns nothing — `POST /matching/swipe` only ever returns `{matched, match_id}` in the HTTP response. The swiping user gets their answer immediately; the *other* user currently only finds out next time they load `GET /matching/matches`, not live as spec.md describes. **Decision**: left as a documented, confirmed cut rather than fixed in this pass — the fix is small (~10 lines in `matching/service.py`, reusing `shared/ws.py`'s `ws_manager.send_event` exactly as `chat` already does), but closing it wasn't done unprompted during an audit pass without confirming the team actually wants it now vs. tracked for later.
3. **None of the four `except IntegrityError` sites verify which constraint actually fired — ADR-0009 explicitly requires it.** ADR-0009's own "Consequences" section: *"Correctness depends on catching the specific unique-violation exception... and verifying its constraint name/columns match the Match pair constraint — catching too broadly would silently swallow unrelated integrity errors as 'already matched.'"* The four sites that rely on this idiom — `auth.signup` (duplicate email), `matching.swipe`'s swipe-insert catch, `matching.swipe`'s match-insert catch, and `chat.send_message` (duplicate `client_message_id`) — all catch bare `IntegrityError` and infer "already exists" by re-querying afterward, without ever inspecting `exc.orig`'s constraint/diag name as the ADR prescribes. In practice this is currently safe by elimination (every FK target on each insert is pre-validated, so the named unique constraint is the only plausible cause left) — but that's exactly the reasoning the ADR warns against substituting for actual verification: a future column, a new constraint, or any other integrity error on that table would be silently absorbed as "already exists" instead of surfacing as the real bug it is. **Decision**: left as a documented, confirmed cut rather than implemented in this pass — the fix is small and mechanical (check `exc.orig.diag.constraint_name` at all four sites, re-raise if it doesn't match), but it's a cross-cutting change to every unique-constraint-race handler in the codebase, worth doing deliberately rather than folding into an audit pass.

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
