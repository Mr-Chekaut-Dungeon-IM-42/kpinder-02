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
