# Keyset (cursor) pagination over offset pagination for lazy-loaded lists

- Status: accepted
- Date: 2026-10-08

## Context

Two lists now need "lazy load 20, scroll for the next 20" pagination: a user's matches (`GET /matching/matches`) and a conversation's messages (`GET /chat/{match_id}/messages`). Both lists grow from the *end* while a client is actively scrolling them — a new match can be created, or a new message sent, while the user is mid-scroll through older pages.

## Decision

Both endpoints use keyset (cursor) pagination: the client passes the id (or `created_at`) of the last item it saw, and the server returns the next 20 strictly older than that cursor (`WHERE created_at < :cursor ORDER BY created_at DESC LIMIT 20`), not a page number or row offset.

## Alternatives considered

Offset pagination (`LIMIT 20 OFFSET 20`, `OFFSET 40`, ...) is the more familiar/simpler-to-implement option and was the initial default. It was rejected: offset pagination's correctness depends on the underlying row order being stable across requests, which it isn't here — if a new match or message is inserted while a user is scrolling, every row after it shifts position by one, and the next `OFFSET` either re-shows an item already seen (duplicate) or silently skips one entirely. For matches/messages specifically, "a message silently disappears from the scrollback because someone else sent one while you were scrolling" is exactly the kind of edge case this lab's audit step is meant to catch, not the kind to accept for simplicity.

## Consequences

Requires an index on the ordering column (`created_at`, or a composite with the id for tie-breaking) for both `Match` and `Message` to keep the keyset query from degrading to a full scan — a straightforward addition to each table's migration, not a new design burden. The API shape is a cursor token/timestamp instead of a page number, which is less familiar to a frontend client but is already necessary infrastructure once correctness under concurrent inserts is a requirement, not a nice-to-have.
