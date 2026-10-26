# 0009 — Lab-5 Follow-up: Co-authorship, Locust Explainers, Local Run Debugging, and Fixing the Two Recorded-Not-Fixed Bugs

Session log: the follow-up conversation after `0008`'s PR was pushed — adding a second co-author, a series of plain explainer questions about how Locust/DI work in this codebase, then debugging the user's own local attempts to run `make seed-load`/`make load`, and finally actually fixing the two bugs that `0008`'s audit had deliberately left as "found, not fixed."

---

### [0009.1] Co-authorship
- **User**: add `Co-authored-by: LobanMihajlo <loban.mihajlo2411@gmail.com>` to the lab-5 PR's commit.
- **AI Action**: Amended the existing (already-pushed) commit to add the line, confirmed with the user before force-pushing (since it had already been pushed), then `git push --force-with-lease`.

### [0009.2] Locust mechanics explainers
- **User**: asked what `n=50k` means for Locust, and what `wait_time` does.
- **AI Action**: Corrected a conflation — 50k is the seeded DB size, not Locust's concurrency (`--users`); explained `wait_time = between(0.5, 2.0)` as the per-simulated-user pacing between task executions, distinct from concurrency.
- **User**: asked whether the `@task(10)`/`@task(6)`/etc. weights mean "10 feed requests, then 6 swipes."
- **AI Action**: Corrected this too — they're relative weights for one random weighted pick per loop iteration (≈45%/27%/14%/9%/5% of 22), not a fixed sequence; walked through the per-user loop mechanics.

### [0009.3] DI rationale explainer
- **User**: asked what the ports-based DI in `libs/matching-core` actually achieves, and why it's needed over ADR-0019's existing constructor injection.
- **AI Action**: Contrasted the old brittle test style (mocked `AsyncSession`, string-path `patch()` on `app.matching.queries.repository.*`) against the new one (plain `FakeRepository`/`FakePhotoResolver`, zero mocking framework), and explained why ADR-0019's concrete-type injection doesn't by itself make a module infra-agnostic — only an abstract `Protocol` the library owns does.
- **User**: asked where `PhotoUrlResolver`'s concrete implementation actually lives.
- **AI Action**: Pointed to `StoragePhotoUrlResolver` in `app/matching/adapters.py`, and explained its relationship to the pre-existing, broader `PhotoStorage` abstraction (`app/shared/storage.py`) it narrows down.

### [0009.4] Debugging the user's own local `make seed-load`/`make load` runs
A multi-round, real-environment debugging session — the user hit a sequence of genuine local-environment mismatches while trying to run the Lab-5 tooling themselves:
1. `ConnectionRefusedError` to `127.0.0.2:5433` — **AI** diagnosed that nothing was running there yet and offered to bring the stack up; user indicated they'd drive it.
2. Wrong host/scheme in a self-made `Makefile` edit (`LOAD_DATABASE_URL:...` missing the `-` for default-value syntax, pointed at `localhost`) — **AI** identified the typo (bash substring-extraction syntax vs. default-value syntax) and the real cause (DB actually bound to `127.0.0.2`, not `localhost`), fixed the Makefile default to match reality and the script's own `postgresql://` (no `+asyncpg`) requirement.
3. `UniqueViolationError` on re-running `make seed-load` — **AI** explained the seed script's deterministic emails collide on re-run without a truncate first, gave the truncate command, and offered (not yet taken up) to make the script itself idempotent.
4. `locust`'s "didn't have proper args" greenlet errors + `ConnectionRefusedError` on `/auth/login` during `make load` — **AI** identified the greenlet errors as cosmetic shutdown-path noise (not the real bug) and the real cause as `make load`'s default host (`127.0.0.6:8000`) not matching where the user's backend was actually running (`127.0.0.2:8000`, from their own `backend/.env`'s `APP_HOST`).
5. `500 Internal Server Error` on `/auth/login` after fixing the host — **AI** found `backend/.env`'s own `DATABASE_URL` still pointed at `localhost:5432` (same host-mismatch bug as #2, now on the app side) and fixed it to `127.0.0.2:5432`, noting the running `--reload` process would need a manual restart to pick up the `.env` change.
6. **User**: asked why a percentile table showed `20000` repeated across every endpoint's 99.9/99.99/100% columns.
   - **AI Action**: Explained Locust's "(approximated)" percentile table buckets response times into exponentially-spaced histogram bins for memory efficiency — `20000` is a bucket label, not a literal shared ceiling — and pointed to the real (non-bucketed) `Max` values in the summary table just above it as the genuine numbers. Also flagged, unprompted, that the run's actual latencies (p50 ~2-3s) were far worse than the audit's documented baseline, and named three likely reasons (`--reload` overhead, other local processes competing for CPU, latency climbing within the run) without being asked to diagnose further.

### [0009.5] Fixing `auth.LoginCommand`'s blocking Argon2 call (previously recorded-not-fixed)
- **User**: asked to fix the bug `ai/audit/lab-5.md` Part B.1 had described as "real... recorded here rather than fixed."
- **AI Action**: Made `hash_password`/`verify_password` (`app/shared/security.py`) `async`, running Argon2 via `anyio.to_thread.run_sync`; updated both call sites (`SignupCommand`, `LoginCommand`) and the one test file constructing hashes directly. Re-ran the exact same 150-concurrent, login-in-the-mix Locust scenario against the fix (reusing the user's own already-running, already-reloaded backend) and confirmed empirically — not just via passing unit tests — that throughput recovered from ~35 req/s to ~69 req/s, matching the previously-isolated no-login range. Updated `ai/audit/lab-5.md` (B.1, B.3, top-3), `DEFENSE.md` (bug description, top-3, known gaps) to describe this as fixed rather than deferred. Committed and pushed with both co-author lines already included from [0009.1].

### [0009.6] Fixing the sequential photo-URL-resolution finding (previously recorded-not-fixed)
- **User**: asked to fix `ai/audit/lab-5.md`'s "secondary finding" — `FeedService.get_feed`'s sequential `await`-per-candidate photo resolution.
- **AI Action**: Changed `feed.py` to resolve all returned candidates' photo URLs concurrently via `asyncio.gather`. Added `test_photo_urls_are_resolved_concurrently`, a regression test designed to prove the *concurrency* itself (a fake resolver that only unblocks once every candidate's `resolve()` call has started, so a reversion to sequential awaits times out instead of silently passing) — verified this works as intended by temporarily reverting `feed.py` to the sequential version locally, confirming the new test actually fails (`TimeoutError`), then restoring the fix. Updated ADR-0026 (amended its "behavior-preserving" framing to carve out this one in-scope fix), `ai/audit/lab-5.md`, and `DEFENSE.md` accordingly. Committed and pushed with both co-author lines.

### [0009.7] This file
- **User**: "add all prompts to ai/prompt."
- **AI Action**: Reviewed `ai/README.md`'s convention and the existing `0005`/`0006` split (grilling session vs. implementation session), and wrote three new session logs for lab-5 (`0007`, `0008`, this file) rather than one, matching that precedent. Did not add a new `ai/audit/lab-5.md` corner-cutting entry beyond what that file already documents, since its existing top-3 (Part D) already serves that role for this lab.
