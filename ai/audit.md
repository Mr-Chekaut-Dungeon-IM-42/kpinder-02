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

Unlike Part A, these are gaps found by auditing the *actual code* against what `spec.md`/the ADRs say should exist — not things the team consciously decided to cut. Each is either fixed in this pass or logged here as a now-deliberate, tracked gap.

### Top-3 undocumented cut corners

1. **`chat` slice has zero automated tests.** `backend/app/auth/tests/` and `backend/app/matching/tests/` both carry unit tests (repository mocked) plus a testcontainers integration test for their respective races (duplicate-email, concurrent mutual-like); `backend/app/chat/` has no `tests/` directory at all. This violates `standards/DEFINITION_OF_DONE.md` item 2 ("Unit tests for any slice the PR touches") and the per-slice layering convention spec.md itself lays out (`tests/` — unit + integration, listed as part of every slice's standard internal structure). Nothing in CI or the pre-push hook caught it, because `pytest` doesn't fail on "no tests collected" for a package — it's a true silent gap, not a documented scope cut. **Decision**: deferred to `feat/lab-3`, not fixed on this branch — lab-2's scope is closing out auth/matching/chat functionality; chat's test suite is explicitly planned as lab-3 work rather than squeezed into this PR. Recorded here so that's a tracked, conscious deferral rather than a silent gap.
2. **`GET /matching/feed`'s candidate query was unbounded — the `limit` parameter was dead code.** spec.md §3.3.1 explicitly promises the feed is "capped at a fixed page size." `matching/repository.py`'s `get_candidates(db, caller, radius_km, limit)` accepted a `limit` argument and never applied it to the query; `get_feed()` called it with `limit=500` expecting the database to cap the result set, but every row matching the radius/gender/seeking/age filters was fetched into Python (with interests eager-loaded) before the Jaccard sort-and-slice. At real scale (a dense city, generous radius) this is unbounded memory and latency — the exact failure mode spec.md's "no obvious N+1" audit bar exists to catch, just a different shape (fetch-everything instead of one-row-per-loop). **Fixed in this pass**: `.limit()` is now actually applied, with an explicit `.order_by(User.id)` underneath it — `LIMIT` without `ORDER BY` is non-deterministic in Postgres, so the pre-cap needed a stable order to mean anything.
3. **Matching's age-range filter is one-directional, not mutual.** A candidate's `age` must fall inside the caller's `age_min`/`age_max`, but the caller's own age is never checked against the candidate's stated preference — so a 60-year-old whose own range is wide enough still appears in an 18-year-old's feed, as long as the 18-year-old's range happens to include 60. This was a judgment call made implementing phase 3 (spec.md §3.3.1 just says "age range," singular and ambiguous on directionality) and was never written back into spec.md or logged here — the kind of silent interpretation-gap this audit exists to surface. **Decision**: left as-is, confirmed with the team — it's a defensible reading of spec.md's ambiguous "age range" wording (one-directional: "I only want to see people in my range"), not a bug, and not worth a unilateral semantics change during an audit pass. Recorded here so it's a conscious choice going forward rather than a silent gap.

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
