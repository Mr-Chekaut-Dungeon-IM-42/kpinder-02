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
