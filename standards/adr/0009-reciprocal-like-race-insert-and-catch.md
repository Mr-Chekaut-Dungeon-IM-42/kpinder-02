# Insert-and-catch-unique-violation for the reciprocal-like race

- Status: accepted
- Date: 2026-10-08

## Context

ADR-0006 commits to mutual-like matching, with a `Match` created only once both users have liked each other, enforced by a unique constraint on the normalized `(user_a_id, user_b_id)` pair. That leaves open *how* the race is resolved when both users swipe `like` on each other within milliseconds: both requests insert their own `Swipe` row, then each must check for the reciprocal `like` and (if found) insert exactly one `Match` row — never zero, never two, and never an unhandled error surfaced to either client.

## Decision

Resolve the race with insert-and-catch, not prevent-then-check: within one transaction, insert the caller's `Swipe` row, query for a reciprocal `like`, and if found, insert the `Match` row. Both concurrent transactions take this same path; the unique constraint on `(user_a_id, user_b_id)` lets only one of the two `Match` inserts succeed. The transaction that loses the race catches the resulting `IntegrityError` and treats it as "match already exists" — an idempotent success, not an error — rather than retrying or propagating a failure.

This same mechanism, and the same idiom (insert, catch the unique-violation, treat it as the already-exists case), is reused for `auth`'s duplicate-email registration race and `chat`'s message-resend dedup (`client_message_id`), so the backend has one consistent pattern for every unique-constraint race rather than a bespoke mechanism per slice.

## Alternatives considered

- **`SELECT ... FOR UPDATE` row lock** — lock the `(user_a_id, user_b_id)` pair (or a derived advisory lock key) before checking reciprocity, serializing the two concurrent transactions so only one ever reaches the insert. Rejected as the default: it prevents the race from occurring at all rather than resolving it after the fact, which is more defensive, but it introduces explicit lock-acquisition-order reasoning and deadlock risk (two swipes forming a cycle between the same two users) that insert-and-catch avoids entirely by never holding a lock across the check.
- **`SERIALIZABLE` isolation with retry-on-conflict** — run the swipe→match transaction at `SERIALIZABLE` and let Postgres abort one of the two concurrent transactions with a serialization failure (`40001`), retried once by the service layer. Rejected: the strongest correctness guarantee of the three options, but it requires an explicit retry-on-40001 policy as a new piece of infrastructure (and a decision about how many times to retry and what to do if retries are exhausted) for a guarantee the unique constraint already provides on its own.

## Consequences

Correctness depends on catching the *specific* unique-violation exception (not a bare `except Exception`) and verifying its constraint name/columns match the `Match` pair constraint — catching too broadly would silently swallow unrelated integrity errors as "already matched." Verified with an integration test that opens two real DB sessions, interleaves their transactions against a real (testcontainers) Postgres, and asserts exactly one `Match` row exists with no unhandled exception on either path; a unit test that mocks the repository to raise `IntegrityError` directly is kept alongside it to prove the catch-handler itself behaves correctly, but does not substitute for the integration test, since it assumes the race fires rather than proving the real constraint does.
