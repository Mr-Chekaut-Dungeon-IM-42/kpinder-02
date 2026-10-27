# 0010 — Lab-5 Flamegraph Analysis, Frontend Accessibility, and Final Audit

Session log: the concluding session of Lab 5 — analyzing the live `py-spy` top profiling and `.svg` flamegraph to verify event-loop offloading and CPU/I/O distribution, auditing and fixing frontend accessibility/contrast/landmarks, structuring the 6 cut corners evenly between both students (3+3), and verifying full readiness.

---

### [0010.1] Interpreting `py-spy` live top profiling
- **User**: Provided live `py-spy top --idle` output:
  - `wait (threading.py)`: 800% own / total time (~2006s)
  - `run (asyncio/runners.py)`: 100% total time (119.7s)
  - `verify_secret (argon2/low_level.py)`: 0.00% own, 22.69s total time
  - SQLAlchemy ORM routines (`_instance`, `_populate_full`, `chunks`)
  - GIL: 0.00%, Active: 6.00%, Threads: 9
- **AI Action**: Diagnosed and explained the thread architecture:
  1. The 800% wait time represents 8 AnyIO worker threads in the threadpool parked in `threading.py` waiting on work.
  2. `verify_secret` had 0.00% own time in the main loop thread, confirming the Argon2 offloading fix was functioning properly in worker threads without stalling the event loop.
  3. GIL contention was 0.00% and Active CPU was only 6.00%, proving the service was overwhelmingly I/O-bound rather than compute-locked.

### [0010.2] SVG flamegraph analysis (`kpinder_flame.svg`)
- **User**: Asked what the generated `kpinder_flame.svg` flamegraph actually means.
- **AI Action**: Deconstructed the 36,507 sampled stack frames from the SVG:
  1. *Stack 1 (87.01%, 31,763 samples)*: Worker threadpool idle wait (`threading.wait`).
  2. *Stack 2 (5.62%, 2,051 samples)*: Background Argon2 password verification (`anyio` threadpool -> `argon2/low_level.py`), physically isolated from the event loop.
  3. *Stack 3 (5.47%, 1,997 samples)*: Main asyncio event loop processing all HTTP traffic (`uvicorn` -> `fastapi` -> `matching_core`).
  4. Highlighted that pure matching/ranking logic (`matching_core/feed.py`) accounted for only 0.18% of samples, confirming candidate pool reduction (from 500 to 50) eradicated the former ORM hydration bottleneck.

### [0010.3] Updating `ai/audit/lab-5.md` with py-spy profiling results
- **User**: "онові аудит, додай результати прогону py-spy"
- **AI Action**: Updated `ai/audit/lab-5.md` to introduce Part B.5 (`B.5.1 Live Top Mode`, `B.5.2 SVG Flamegraph Analysis`), embedding exact numeric timings, thread sample counts, and architectural explanations.
- **User**: Followed up to ensure the py-spy audit was thoroughly recorded in the markdown audit file.
- **AI Action**: Confirmed and finalized the py-spy section formatting and persistency in `ai/audit/lab-5.md`.

### [0010.4] Frontend accessibility, WCAG contrast, and SEO fixes
- **User**: "let's fix frontend now, what should be done here?"
- **AI Action**: Identified the three required frontend improvements per spec and Lighthouse requirements:
  1. *WCAG AA contrast failure*: Pink accent `#e8457a` had a 3.77:1 contrast ratio against `#ffffff` (minimum required is 4.5:1).
  2. *Landmarks*: Missing `<main>` semantic landmark on page views.
  3. *SEO & Meta tags*: Missing `<meta name="description">` and `robots.txt`.
- **User**: "yes" (approved implementation).
- **AI Action**: Implemented all fixes across the frontend workspace:
  - Replaced `#e8457a` with WCAG AA compliant `#c2255c` (contrast ratio 5.66:1) in `NavBar.module.css`, `AuthForm.module.css`, `Chat.module.css`, `Feed.module.css`, `Matches.module.css`, and `Profile.module.css`.
  - Wrapped views with `<main className={styles.page}>` across `Feed.tsx`, `Matches.tsx`, `Chat.tsx`, `Profile.tsx`, `Login.tsx`, and `Register.tsx`.
  - Added meta description and theme color to `index.html`.
  - Created `public/robots.txt`.
  - Formatted files with Prettier and verified clean builds with `npm run lint` and `npm run build`.

### [0010.5] Audit Part C & D finalization (6 Cut Corners split 3+3)
- **AI Action**: Updated `ai/audit/lab-5.md`:
  - Updated Part C with frontend audit results and post-fix notes.
  - Structured Part D into an even 3+3 distribution across both students:
    - *Student 1 (Ivan Fedorenko)*: Over-fetching candidate pool, Argon2 event loop block, Sequential photo URL awaits.
    - *Student 2 (Loban Mihajlo)*: Missing composite B-tree indexes, Monorepo Docker context & `--no-dev`, Frontend WCAG AA contrast & `<main>` landmarks.
  - Marked all 6 cut corners as `[FIXED]` with empirical before/after metrics.

### [0010.6] Readiness verification (skipping defense part)
- **User**: "check if lab5 is ready, skip defense part"
- **AI Action**: Executed full automated verification suite:
  - `libs/matching-core` unit tests: 12 passed.
  - `backend` test suite: 82 passed.
  - Frontend: clean Vite production build.
  - Alembic migrations: verified up to date (`fe77c7523aa3`).
  - Confirmed `DEFENSE.md` was skipped/omitted per user instructions.
  - User committed and pushed the changes (`f84f731`).

### [0010.7] Compaction into `ai/prompts/`
- **User**: "/compact into ai/prompts"
- **AI Action**: Recorded this sequential session log as `ai/prompts/0010-lab5-flamegraph-frontend-audit-and-finalization.md`, concluding the Lab 5 prompt history.
