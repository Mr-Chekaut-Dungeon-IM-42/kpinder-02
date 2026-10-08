# 0003 — Lab-2 Planning Interview (`/grill-me`)

Session: a `/grill-me` run over the lab-2 brief (scenarios on static data → real DB; schema/queries/error scenarios in `spec.md`; audit for N+1/transactions/idempotency; `DEFENSE.md` + ADRs on DB/ORM choice). No implementation happened in this session — the output is a plan (`spec.md`/ADR updates + this file) for a later session to execute against.

---

**[0003.1]** Prompt: *lab-2 brief, pasted in Ukrainian — core scenarios first on static data, then real DB; spec.md; audit for cut corners/N+1/failure handling; DEFENSE.md + ADR on DB/ORM.*
- **AI Action**: Read `spec.md`, `standards/DEFINITION_OF_DONE.md`, `README.md`, `standards/adr/*`, `backend/app/main.py`, `ai/audit.md`. Found none of the three slices (`auth`/`matching`/`chat`) have any code yet — lab-1 only scaffolded the repo. Asked which slice(s) are in scope given the timeline.
- **User**: all three slices, but clarified this session only produces a **plan** for another Claude session to execute — no implementation here.

**[0003.2]** Prompt (AskUserQuestion): static-data-phase design (repository interface + in-memory fake, vs fixture-returning repo, vs env-toggled dual-mode).
- **User**: "we're not implementing static, it's fine" — deferred the design-shape question since it wasn't going to be implemented this session.

**[0003.3]** Prompt (AskUserQuestion): whether to write a new ADR for DB/ORM choice given lab-2's explicit ask, despite `spec.md` §6 saying ADRs are only for contested decisions.
- **User**: chose to point to existing ADR-0005 + a `spec.md` §6 note instead of writing a new one. **Risk accepted**: may read as dodging the brief's explicit ask (`ai/audit.md` Part A #8).

**[0003.4]** Prompt (AskUserQuestion): swipe→match concurrency mechanism (insert-and-catch-unique vs `SELECT...FOR UPDATE` lock vs `SERIALIZABLE`+retry).
- **User**: insert-and-catch-unique-violation (**AI's recommendation**).

**[0003.5]** Prompt (AskUserQuestion): swipe retry/idempotency semantics.
- **User**: initially proposed allowing "unlike" to delete an existing `Match` (full CRUD on `Match`/`User`) — a real scope change from ADR-0006's "append-only" framing.

**[0003.6]** Prompt (AskUserQuestion): asked to confirm the ADR-0006 update + message-cascade behavior for the unmatch design from [0003.5].
- **User**: reversed course — "adr makes swipe append only and thus we do not allow to unlike and delete a match, move on." No unmatch, no `Match` deletion. Retry semantics settled as: same decision on retry → idempotent 200; different decision on retry → `409 Conflict`.

**[0003.7]** Prompt (AskUserQuestion): `GET /matching/candidates` query shape to avoid N+1 (single query w/ `selectinload`+`NOT EXISTS` vs two explicit queries).
- **User**: single query, `selectinload`/`joinedload` + `NOT EXISTS` subquery (**AI's recommendation**).

**[0003.8]** Prompt (AskUserQuestion): DB/source failure handling (global 503 handler + `pool_pre_ping`, no retry vs same + bounded read-only retries).
- **User**: global handler + `pool_pre_ping`, no app-level retry at all (**AI's recommendation**, narrower of the two offered variants).

**[0003.9]** Prompt (AskUserQuestion): chat message idempotency (client-supplied `client_message_id` unique constraint vs no dedup, documented cut).
- **User**: client-supplied `client_message_id`, unique on `(match_id, sender_id, client_message_id)` (**AI's recommendation**).

**[0003.10]** Prompt (AskUserQuestion): where to capture today's decisions (fold into `spec.md`+new ADR+`ai/prompts/` vs standalone `PLAN.md`).
- **User**: "spec+adr+ai/prompts" — fold into `spec.md` as the authoritative target design, update the relevant ADR (0006), and log this file.

**[0003.11]** Prompt (AskUserQuestion): how to test the swipe-race handling (real concurrent-transaction integration test vs mocked-`IntegrityError` unit test).
- **User**: real concurrent-transaction integration test against testcontainers Postgres (**AI's recommendation**) — kept alongside (not instead of) a unit test for the catch-handler itself.

**[0003.12]** Prompt (AskUserQuestion): `DEFENSE.md` timing (scaffold now vs leave entirely to the executing session).
- **User**: "do not touch defence.md" — explicitly left untouched; it's the executing session's final step before opening the PR.

**[0003.13]** Prompt (AskUserQuestion): revisited whether to keep or skip the static-data phase given [0003.2] vs the brief's explicit DoD requirement.
- **User**: skip it entirely, go straight to DB integration — accepted as a deliberate, documented scope cut (`ai/audit.md` Part A #7), with the explicit risk of losing DoD points for it.

**[0003.14]** Prompt: auth register-race consistency check (insert-and-catch-unique → `409`, same idiom as swipe/message).
- **User**: confirmed — same idiom across register/swipe/message, no bespoke check-then-insert anywhere in the backend.

**[0003.15]** Prompt: *"I'll write the files, you review and commit yourself"* (AskUserQuestion on commit handling).
- **AI Action**: Updated `spec.md` (§3 scenarios: register/swipe/match/message mechanisms + new "DB/source failure handling" subsection; §4 scoped-out: static phase + no-unmatch; §6: DB/ORM ADR note), `standards/adr/0006-swipe-mutual-match.md` (Consequences: append-only reaffirmed, race mechanism detailed), `ai/audit.md` (Part A #7–8), and this file. No git commit created — left for the user to review and commit.
