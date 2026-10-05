# 0001 — Architecture grilling (`/grill-me`)

Session: shaping the Kpinder MVP architecture via `/grill-me`, from initial idea to `spec.md`. Condensed log — each entry is one exchange: the human's prompt, the AI's recommendation/action, and the outcome.

---

**[0001.1]** Prompt: *"i with friend want to develop dating service named kpinder for uni project... mvp: auth, matching, chat; vertical slices; testing"*
AI: read `README.md`, identified this is Lab 1 (scaffolding + standards + `spec.md`), not a full build. Asked about timeline/checkpoints.
Outcome: human said not to worry about time.

**[0001.2]** Prompt: *"react, python, sqlalchemy, alembic, postgres"*
AI: asked for the Python web framework.

**[0001.3]** Prompt: *"FastAPI, let's keep going"*
AI: recommended monorepo.

**[0001.4]** Prompt: *"monorepo, vertical slices"*
AI: confirmed vertical-slice architecture; asked about cross-slice shared concerns.

**[0001.5]** Prompt: *"yes, keep going"*
AI: recommended a `shared/core` module (DB session, JWT dependency, core models) that slices depend on, never each other.

**[0001.6]** Prompt: *"yes, keep going"*
AI: proposed per-slice internal layering, **recommended skipping a repository layer** ("indirection you don't need yet").
Human feedback: *"no, add repo layer as well."*
→ **Correction.** See `audit.md` #1.

**[0001.7]** Prompt: *"yes, keep going"* (frontend mirrors vertical slices)
AI: confirmed feature-folder frontend structure.

**[0001.8]** Prompt: *"yes, keep going"*
AI: recommended JWT auth, no refresh rotation for MVP.

**[0001.9]** Prompt: *"yes, keep going"*
AI: **recommended polling over WebSockets** for chat, citing connection-lifecycle complexity; explicitly asked whether the instructor expects WebSockets specifically.
Human feedback: *"no, we want websockets."*
→ **Correction.** See `audit.md` #2.

**[0001.10]** Prompt: *"yes, keep going"*
AI: recommended in-memory single-process WS connection registry (not Redis-backed) — accepted as-is.

**[0001.11]** Prompt: *"yes, keep going"*
AI: **recommended in-app-only, ephemeral notifications** — no DB table, no offline delivery.
Human feedback: *"no we want to have ... persistent/offline notifications (stored in DB, visible next time you log in, maybe push notifications)"* — and in the same message, asked for Redis as a cache (candidates, TTL 10 min) and a message broker.
→ **Correction.** See `audit.md` #3.

**[0001.12]** Prompt: *"event bus via redis pub/sub, keep going"*
AI: proposed `notifications` as its own 4th slice, subscribing to `matching`'s and `chat`'s published events.

**[0001.13]** Prompt: *"yes"* / *"yes, keep going"*
AI: confirmed WS connection registry lives in `shared/`, not owned by `chat`.

**[0001.14]** Prompt: *"yes, keep going"*
AI: proposed candidate-list caching (not pairwise scores) under `candidates:{user_id}`, TTL-only invalidation.

**[0001.15]** Prompt: *"yes, keep going"*
AI: proposed swipe-based matching, mutual-like → `Match`.

**[0001.16]** Prompt: *"yes, keep going"*
AI: **recommended plain lat/lng + Haversine SQL**, explicitly against PostGIS, citing "unnecessary dependency" / audit-step risk.
Human feedback: *"let's use postgis, simple queries and native geo support."*
→ **Correction.** See `audit.md` #1 (grouped with the repository-layer walk-back as a pattern of AI defaulting to "fewer dependencies").

**[0001.17]** Prompt: *"yes, keep going, we do not want to match hiking and hikeing and that would also require us to validate user input"*
AI: confirmed curated `Interest` tag table (many-to-many) over free text.

**[0001.18]** Prompt: *"yes, keep going"*
AI: proposed gender/seeking/age-range as hard filters alongside the radius filter.

**[0001.19]** Prompt: *"what's the simplest way to store photo without paying for infra?"*
AI: recommended local-disk storage with randomized filenames + content-type validation; proposed folding photo upload into `auth`.

**[0001.20]** Prompt: *"no, we want to have slices: auth, matching, chat, notifications, profile"*
AI: accepted 5-slice split; raised the resulting boundary question (where does `Profile` live if `matching` needs to read it).

**[0001.21]** Prompt: *"fair point, let's move to layered architecture"*
AI: asked for clarification (full revert to horizontal layering vs. "move to the next topic") rather than assuming — this was a genuine ambiguity, not a cut corner.

**[0001.22]** Prompt: *"draft diagrams for slices and layered architecture"*
AI: loaded `artifact-design`/`artifact-diagramming`, published the architecture artifact (system diagram + layering diagram + resolved-decisions reference).

**[0001.23]** Prompt: *"move profile to auth and keep slices"*
AI: reverted to 4 slices (`auth` incl. profile), updated the artifact.

**[0001.24]** Prompt: *"yes"* (testcontainers + real Postgres/PostGIS for integration tests)
AI: confirmed, citing that SQLite can't run PostGIS queries.

**[0001.25]** Prompt: *"backend-only for now, keep going"*
AI: confirmed frontend tests out of scope for this lab, documented as a gap.

**[0001.26]** Prompt: *"yes, keep going"*
AI: recommended `pre-commit` framework over Husky (language-agnostic, covers both stacks).

**[0001.27]** Prompt: *"yes, add mypy, keep going"* → **[0001.28]** Prompt: *"no mypy, only ruff / typescript"*
AI: adjusted tooling choice per the correction; no spec impact beyond tooling list.

**[0001.29]** Prompt: *"only in CI"*
AI: confirmed integration tests run in CI only, not local pre-push.

**[0001.30]** Prompt: *"just 2-3 sentences about stack ... "*
AI: narrowed ADR scope to contested decisions only; routine stack picks get a short blurb instead.

**[0001.31]** Prompt: *"yes"* (teammate review required before merge)

**[0001.32]** Prompt: *"yes, keep going"* (DoD checklist + docker-compose for local dev)

**[0001.33]** Prompt: *"yes, keep going"* (`Swipe` table recording both like/pass, not just likes)

**[0001.34]** Prompt: *"no we want this"* (read receipts)
AI had recommended skipping read receipts as a nice-to-have; human wanted them. Minor correction — not in the top-3 (schema addition only, no architectural rework), but noted here for completeness.

**[0001.35]** Prompt: *"yes, keep going"* (read receipts delivered via direct WS push, not the event bus — correctly scoped as intra-slice)

**[0001.36]** Prompt: *"we need stage, prod env"*
AI had recommended local-only deployment, citing it wasn't asked for in the README. Human corrected: stage + prod are required.
→ Noted as a scope correction (not a "cut corner" in engineering judgment — the AI's read of the grading rubric was reasonable, but incomplete relative to the team's actual requirement).

**[0001.37]**–**[0001.42]** Railway (PaaS over self-managed VPS), single-branch + manual-promotion deploy model, pydantic-settings config, integration tests as required PR checks — all accepted as proposed.

**[0001.43]** Prompt: *"update the artifact and let's write spec.md"*
AI: updated the artifact, wrote `spec.md`.

**[0001.44]** Prompt: AI-trail requirement (`ai/` prompt log + top-3 cut-corners audit) added to the project's deliverables.
AI: created this file and `audit.md`.
