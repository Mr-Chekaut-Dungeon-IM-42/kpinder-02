# Hard delete for messages (not soft-delete/tombstone)

- Status: accepted
- Date: 2026-10-08

## Context

`DELETE /chat/messages/{message_id}` (spec.md §3) needs a deletion semantics. The initial design used a soft-delete (`deleted_at` column, `content` tombstoned to e.g. "message deleted") on the stated grounds that a hard delete would destabilize keyset-pagination cursors (ADR-0012) for a client mid-scroll. That reasoning was wrong: keyset pagination keys off a value (`created_at`/id) on the *remaining* rows, not row position or count, so removing a row doesn't shift any other row's cursor — that's precisely the class of bug keyset pagination exists to avoid, and it applies here too. With that objection removed, the choice is a plain simplicity-vs-audit-trail tradeoff.

## Decision

`DELETE /chat/messages/{message_id}` hard-deletes the `Message` row. Only the original sender may delete their own message (`403` otherwise). Deleting an already-deleted (i.e. no-longer-existing) message returns `404` — repeating the same `DELETE` request always ends with the resource absent, which is idempotent in the sense HTTP's semantics require, even though the second response's status differs from the first's `204`. `PATCH /chat/messages/{message_id}` on a hard-deleted message likewise returns `404` (not `409` — there's no soft-deleted row left to conflict with).

## Alternatives considered

Soft-delete (`deleted_at` + tombstoned `content`, row retained) was the initial design. Rejected once the pagination-stability justification for it turned out not to hold: keyset pagination doesn't require the deleted row to still exist. What's left in soft-delete's favor is an audit/moderation trail (what was said before it was deleted) and a "this message was deleted" placeholder shown in the other side's history — neither is a stated requirement for this lab, and keeping them would mean every message query filters on `deleted_at IS NULL`, extra schema (one column), and extra service-layer logic for no requirement it serves. Hard delete was chosen as the simpler option given nothing currently needs the trail.

## Consequences

A deleted message leaves no trace in `GET /chat/{match_id}/messages` or search — anyone paginating back later (or a future moderation need) sees nothing, not even that something was removed. The live WS "deleted" push (spec.md §3) is the only record the other participant gets that a message existed and was removed, and only if they were connected at the time. If a moderation/audit requirement emerges later, reintroducing it is a straightforward schema addition (an `audit_log`-style table outside the hot `Message` read path, rather than reviving tombstoning inline) rather than a reason to keep the column now. `Message.edited_at` is unaffected by this decision — edits remain in place (`PATCH` updates `content` and sets `edited_at`); only delete changed from soft to hard.
