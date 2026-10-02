# Kpinder — Spec

Dating service MVP. Monorepo: `backend/` (Python, FastAPI) + `frontend/` (React, TypeScript, Vite).

Architecture, decisions, and rationale are visualized at: https://claude.ai/code/artifact/d5c8553c-b34f-4e08-ba3d-59f51a836829

## 1. Components

Backend is organized as **vertical slices** — one bounded context per feature, not horizontal layers spanning the whole app. A slice owns its router, service, repository, and (where applicable) its own tables. Slices never import another slice's router or service.

| Slice | Owns | Depends on |
|---|---|---|
| `auth` | login, registration, JWT issuance, profile management, photo upload | `shared` |
| `matching` | candidate ranking, swipe, match detection | `shared`, Redis (cache + bus) |
| `chat` | 1:1 messaging over WebSocket, read receipts | `shared` |
| `notifications` | persisted notifications, delivery to online users | `shared`, Redis (bus) |

`shared/` (core) is not a slice — it's infrastructure every slice depends on, and never the other way around:
- DB session factory
- JWT-verify dependency (identifies the current user for any slice's router)
- WebSocket connection registry (`user_id → connection`, in-memory, single-process)
- Core data models: `User`, `Profile`, `Interest`, `UserInterest`

A slice's own repository may read `shared`'s tables directly (e.g. `matching` reads `Profile`/`Interest` for candidate ranking) — that's reading shared data, not calling another slice's business logic, so it doesn't violate the no-cross-slice-import rule.

### Internal layering (per slice)

```
router.py       — HTTP/WS endpoints, Pydantic schemas
service.py       — business rules (scoring, match detection, event emission)
repository.py    — SQLAlchemy queries only, no business logic
models.py        — slice-owned tables (reads shared models directly where needed)
tests/           — unit tests (repository mocked) + integration tests (real DB)
```

### Cross-slice communication

Slices that need to react to another slice's events do so via a **Redis pub/sub event bus**, never by importing each other:

- `matching` publishes `match.created`
- `chat` publishes `message.sent`
- `notifications` subscribes to both, persists a `Notification` row, and pushes it live over the shared WS registry if the recipient is connected

A message **read receipt** is the one exception that does *not* go through the bus — both sides of a read receipt are internal to `chat` (sender and recipient are both `chat`'s concern), so `chat`'s service pushes directly over the shared WS registry.

## 2. Data model

```mermaid
erDiagram
    USER ||--|| PROFILE : has
    PROFILE }o--o{ INTEREST : "via UserInterest"
    USER ||--o{ SWIPE : "swiper"
    USER ||--o{ SWIPE : "swiped (target)"
    USER ||--o{ MATCH : "user_a"
    USER ||--o{ MATCH : "user_b"
    MATCH ||--o{ MESSAGE : contains
    USER ||--o{ MESSAGE : sends
    USER ||--o{ NOTIFICATION : receives

    USER {
        uuid id PK
        string email UK
        string password_hash
        datetime created_at
    }
    PROFILE {
        uuid user_id PK_FK
        string name
        int age
        string bio
        string gender
        string seeking
        int age_min
        int age_max
        geography location
        string photo_url
    }
    INTEREST {
        uuid id PK
        string name UK
    }
    SWIPE {
        uuid id PK
        uuid swiper_id FK
        uuid swiped_id FK
        enum decision "like | pass"
        datetime created_at
    }
    MATCH {
        uuid id PK
        uuid user_a_id FK
        uuid user_b_id FK
        datetime created_at
    }
    MESSAGE {
        uuid id PK
        uuid match_id FK
        uuid sender_id FK
        string content
        datetime created_at
        datetime read_at "nullable"
    }
    NOTIFICATION {
        uuid id PK
        uuid user_id FK
        enum type "match_created | message_received"
        uuid reference_id "match_id or message_id"
        datetime created_at
        datetime read_at "nullable"
    }
```

Notes:
- `SWIPE` has a unique constraint on `(swiper_id, swiped_id)` and records both `like` and `pass`, so a passed profile never resurfaces in a future candidate list.
- `MATCH` is created the moment a reciprocal `like` is detected (both directions exist in `SWIPE`).
- Location is stored as a PostGIS `geography(Point)` column; candidate queries filter with `ST_DWithin`.
- Interests are a curated, predefined tag list (not free text) so Jaccard overlap is meaningful — free text would make "hiking" and "hikeing" score as zero overlap.

## 3. Key scenarios — how data updates

### Registration & login (`auth`)
1. `POST /auth/register` — validates input, hashes password, inserts `User` + empty `Profile`.
2. `POST /auth/login` — verifies credentials, issues a JWT (single long-lived access token, no refresh rotation for MVP).
3. All other slices' routers depend on the shared JWT-verify dependency to identify the caller — none re-implement auth.

### Profile management & photo upload (`auth`)
1. `PATCH /auth/profile` — updates `Profile` fields (bio, interests, location, gender/seeking, age range) directly; no cache to invalidate here (candidate cache keys are per-*viewer*, and staleness is bounded by the 10-minute TTL rather than actively busted).
2. `POST /auth/profile/photo` — validates content-type/magic bytes and size, writes to a local disk volume under a randomized UUID filename, stores the resulting `photo_url` on `Profile`.

### Swipe & match (`matching`)
1. `GET /matching/candidates` — checks Redis for `candidates:{user_id}` (TTL 10 min); on miss, queries `Profile` filtered by PostGIS radius + gender/seeking + age range, excluding users already present in `SWIPE`, ranks the rest by Jaccard interest overlap, caches the ordered list.
2. `POST /matching/swipe` — inserts a `SWIPE` row (`like` or `pass`). If a reciprocal `like` already exists for the pair, creates a `MATCH` row and publishes `match.created` on the Redis bus.
3. `notifications` (subscriber) receives `match.created`, inserts a `Notification`, and pushes it live over the shared WS registry if either user is connected.

### Messaging (`chat`)
1. Client opens a WebSocket authenticated via the shared JWT dependency; `chat` registers the connection in the shared WS registry.
2. `send_message` over the socket — validates the sender is part of the `match`, inserts a `Message`, publishes `message.sent` on the Redis bus, and pushes the message directly to the recipient's connection if registered.
3. `notifications` (subscriber) receives `message.sent`, inserts a `Notification` (covers the case where the recipient isn't currently connected).
4. `mark_read` over the socket — sets `Message.read_at`, and `chat` pushes a read-receipt update directly to the sender's connection via the shared WS registry (no bus — this is intra-slice).

### Notifications (`notifications`)
1. `GET /notifications` — lists the current user's `Notification` rows, newest first.
2. `POST /notifications/{id}/read` — sets `read_at`.
3. If the user isn't connected when an event arrives, the `Notification` row is simply picked up next time they call `GET /notifications` — no push retry/offline queue for MVP.

## 4. Scoped out (documented, not built)

- Frontend tests (Vitest/RTL) — backend-only test coverage for this lab.
- JWT refresh-token rotation — single long-lived access token.
- Multi-instance WebSocket scaling — connection registry is single-process; horizontal scaling would need a pub/sub-backed registry (the same Redis bus, extended).
- Rate limiting / abuse prevention.
- Offline push notifications (APNs/FCM) — in-app only, delivered over the existing WebSocket.

## 5. Infra & environments

- **Local**: `docker compose up` — Postgres+PostGIS, Redis, backend, frontend.
- **CI**: GitHub Actions — `ruff`/`eslint`+`prettier`, backend unit tests, integration tests (real Postgres+PostGIS via testcontainers), frontend build. All required checks on every PR into `main`.
- **Staging**: Railway, auto-deploys on every merge to `main`.
- **Production**: Railway, manual-trigger promotion (tagged release) after staging verification.
- **Config**: `pydantic-settings` reads env vars uniformly across local/stage/prod; secrets (DB URL, Redis URL, JWT signing key) are never committed — `.env.example` only.

## 6. Standards

See `standards/` for ADR format (MADR), Definition of Done, and the audit checklist. ADRs are written only for genuinely contested decisions (vertical slices vs layered, shared-core boundary rule, Redis as event bus, WebSockets vs polling, PostGIS vs plain lat/lng, swipe+mutual-match vs auto-match, JWT vs sessions) — not for routine stack picks.

## 7. AI trail

This spec was shaped through an AI-assisted design interview. The full prompt trail is in [`ai/prompts/`](ai/prompts/), and a self-audit of where the AI's suggestions cut corners (and were corrected) is in [`ai/audit.md`](ai/audit.md) — each entry links the originating prompt, the human's correction, and the resulting change to this spec.
