# Swipe + mutual-like matching over auto-matching

- Status: accepted
- Date: 2026-10-02

## Context

"Matching based on similarity" could mean the algorithm directly creates matches above some similarity threshold, or similarity could rank candidates that the user then explicitly accepts/rejects one at a time.

## Decision

Swipe-based matching: `matching` ranks candidates by a radius filter (PostGIS, ADR-0005) followed by Jaccard interest-overlap scoring; the user swipes `like`/`pass` on each candidate (recorded in a `Swipe` table, which stores both decisions so passed profiles don't resurface); a `Match` row is created only when both users have liked each other.

## Alternatives considered

Auto-matching (the algorithm unilaterally decides two users are a match once similarity crosses a threshold) was rejected — it removes the mutual-consent step that's the actual point of "matching" in a dating-app sense, and it's a worse product experience: nobody wants to be told they're matched with someone they never agreed to talk to.

## Consequences

Requires a `Swipe` table distinct from `Match` (see `spec.md` §2) — `Swipe` is an append-only decision log, `Match` is the derived, addressable relationship that `Message` attaches to. The mutual-like detection needs a unique constraint on the normalized `(user_a_id, user_b_id)` pair to handle the race where both users swipe within milliseconds of each other — see ADR-0009 for how that race is actually resolved.
