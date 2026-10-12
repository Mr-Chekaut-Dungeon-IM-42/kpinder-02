# 0004 — Chat Slice & Real-Time WebSockets Implementation

Session: Comprehensive end-to-end design, implementation, architectural alignment, troubleshooting, and verification of the **Chat vertical slice** (`backend/app/chat/`), real-time WebSocket connection manager (`backend/app/shared/ws.py`), and React chat conversation UI (`frontend/src/pages/Chat.tsx`). Testing suites deferred to Lab 3 per explicit user instruction; focus strictly on core functionality, migrations, IDOR security, idempotency, and responsive frontend UX.

---

**[0004.1]** Prompt: *Summarize all changes on `feat/lab-2` branch.*
- **AI Action**: Inspected git tree comparing `origin/main` (Lab 1 scaffold) against `feat/lab-2`.
- Audited implementation status across vertical slices:
  - `auth`: User registration, Argon2id password hashing, JWT access token issuance (ADRs 0002, 0013).
  - `profile`: Profile management, photo upload presigned URLs, GeoJSON location updates via PostGIS points.
  - `matching`: Feed generation, swipe transactions, mutual match detection (ADRs 0006, 0007).
  - `chat`: Documented in `spec.md §3` and ER diagrams, but completely unbuilt in code.
- Noted ADRs 0008 through 0013 introduced during Lab 2 (PostGIS migrations, token handling, hard delete, etc.).

**[0004.2]** Prompt: *Setup example: how to setup a project, install deps, and run it locally?*
- **AI Action**: Detailed local developer environment setup and execution steps:
  - Database: Docker Compose PostgreSQL with PostGIS (`docker compose up -d db` on port 5433).
  - Backend: `uv venv`, `uv sync` to install Python dependencies, configure `.env`, run database migrations via `uv run alembic upgrade head`, and start FastAPI server via `uv run uvicorn app.main:app --reload --port 8000`.
  - Frontend: `npm install` for node dependencies, configure `frontend/.env`, and run Vite dev server via `npm run dev` on port 5173.

**[0004.3]** Prompt: *Do I need to keep a separate `.env` for both frontend and backend? Right now `.gitignore` can't see `.env`.*
- **AI Action**: Clarified configuration and environment variable isolation boundaries:
  - Backend `.env` sits at repository root or `backend/` and parses via `pydantic-settings` (`DATABASE_URL`, `JWT_SECRET_KEY`, `ALGORITHM`).
  - Frontend Vite requires explicit `VITE_` prefix (`VITE_API_BASE_URL`, `VITE_WS_BASE_URL`) at `frontend/.env`. Client-side bundlers only expose variables prefixed with `VITE_` to protect server credentials from leaking into the compiled bundle.
  - Audited `.gitignore` rules to guarantee secrets are ignored while checked-in templates (`.env.example`) remain intact.

**[0004.4]** Prompt: *Check what is done from those for now: Auth (/login, /logout, /signup, /upload_photo, /update_profile), Matching (/feed, /swipe, /get_matches_by_id with lazy loading), Chatting (CRUD for messages, search, real-time WebSockets).*
- **AI Action**: Audited repository against the functional requirement checklist:
  - Auth & Profile: Complete (`/auth/signup`, `/auth/login`, `/profile/me`, `/profile/photo/upload-url`, `/profile/interests`). Logout handled via stateless client-side token discard per ADR-0013.
  - Matching: Complete (`/matching/feed`, `/matching/swipe`, `/matching/matches` with keyset pagination).
  - Chat: Completely missing. No database models, Alembic migrations, REST routers, WebSocket endpoints, or frontend UI existed.

**[0004.5]** Prompt: *`/plan` Explain how to work with WebSockets in FastAPI starting from basics. Write a plan for implementing needed functionality.*
- **AI Action**: Provided detailed conceptual and practical overview of FastAPI WebSockets:
  - Protocol mechanics: HTTP request-response cycle vs bidirectional, persistent full-duplex TCP stream over WebSocket (`ws://` / `wss://`).
  - Connection lifecycle: HTTP 101 Switching Protocols upgrade handshake, persistent event loop (`receive_text()` / `send_json()`), and graceful closure (`WebSocketDisconnect`).
  - Authentication challenges: Standard browser `new WebSocket(url)` API does not support custom `Authorization: Bearer <token>` HTTP headers. Evaluated two strategies: one-time ticket exchange vs query parameter `?token=...`. Chose query parameter with instantaneous validation before accepting the connection handshake.
  - Concurrency & Architecture: In-memory `ConnectionManager` pattern maintaining `dict[UUID, set[WebSocket]]` for single-node development (ADR-0004).
  - Authored initial roadmap: Model & Migration -> WebSocket Manager & JWT Refactor -> Chat Slice Backend -> Frontend Hook & Client -> Chat UI -> Verification.

**[0004.6]** Prompt: *Expand that draft plan step-by-step: start from backend, model, chatting logic -> frontend support -> tests.*
- **AI Action**: Authored detailed implementation roadmap artifact (`chat_websocket_implementation_plan.md`):
  - Phase 1: Shared Models (`Message` entity) & Alembic migration.
  - Phase 2: In-memory WebSocket manager & connection authentication.
  - Phase 3: Chat vertical slice backend (schemas, repository, service, router).
  - Phase 4: Frontend API client methods & `useWebSocket` custom hook.
  - Phase 5: Chat UI page with bubbles, edit/delete actions, search, and keyset lazy loading.
  - Phase 6: Automated tests (unit, integration, mutation).

**[0004.7]** Prompt: *Step 1 — Update shared/models.py, review against spec ER diagram, provide explanations for decisions.*
- **AI Action**: Formulated `Message` entity specification matching `spec.md §3` ER diagram:
  - Fields: `id` (UUID pk), `match_id` (FK to matches.id, CASCADE), `sender_id` (FK to users.id, CASCADE), `client_message_id` (UUID), `content` (VARCHAR(2000)), `created_at` (TIMESTAMPTZ), `updated_at` (TIMESTAMPTZ, nullable).
  - Idempotency Constraint: `UniqueConstraint("match_id", "sender_id", "client_message_id")` ensures network retries never produce duplicate messages.
  - Keyset Pagination Index: `Index("ix_messages_match_created_at_id", "match_id", "created_at", "id")` enables sub-millisecond reverse-chronological tuple paging.

**[0004.8]** Prompt: *How to create a new migration & running alembic upgrade.*
- **AI Action**: Provided commands: `uv run alembic revision --autogenerate -m "create messages table"` and `uv run alembic upgrade head`.
- **User Encountered Error**: Alembic autogenerated ~700 lines of spurious `op.drop_table()` for PostGIS tiger-geocoder tables (`bg`, `cousub`, `tabblock`), terminating with `DependentObjectsStillExistError`.

**[0004.9]** Prompt: *Explain why the migration is broken, cmd used: `uv run alembic revision --autogenerate -m "create messages table"`.*
- **AI Action**: Diagnosed failure: PostGIS extension installs system tables and functions into PostgreSQL. Because SQLAlchemy models do not define these extension tables, Alembic's `--autogenerate` engine assumes they are obsolete application tables and attempts to generate `op.drop_table()` for each.

**[0004.10]** Prompt: *How is it usually fixed? Or will I need to delete those rows manually each time?*
- **AI Action**: Outlined long-term vs immediate solutions:
  - Long-term: Implement `include_object` filter callback in `backend/alembic/env.py` to instruct Alembic to ignore system tables outside application schemas.
  - Immediate: Manually strip out dropped PostGIS tables from the migration script per ADR-0008, keeping only `op.create_table('messages', ...)`.

**[0004.11]** Prompt: *Formatting errors in migration: `Line too long (92 > 88)` with pre-commit linter.*
- **AI Action**: Formatted `backend/alembic/versions/cab730c95c29_create_messages_table.py` to comply with Ruff 88-character line limits.
- Added explicit `downgrade()` implementation (`op.drop_table('messages')`).
- Successfully executed `uv run alembic upgrade head`.

**[0004.12]** Prompt: *Skip testing part, it will be in Lab 3, right now focus only on functionality. Update step-by-step guide.*
- **AI Action**: Updated the step-by-step plan: pruned automated test authoring (unit tests, Testcontainers integration tests, mutmut mutation testing) from the immediate execution plan. Shifted roadmap focus exclusively to completing functional backend endpoints, WebSocket push events, and frontend user interface.

**[0004.13]** Prompt: *`jwt_dep.py` has duplicated code, create a helper function before proceeding to Step 3.*
- **AI Action**: Refactored `backend/app/shared/jwt_dep.py`:
  - Extracted shared token decoding into private helper `_parse_and_validate_token(token: str) -> uuid.UUID`.
  - Reused `_parse_and_validate_token` across both `get_current_user_id` (HTTP Bearer header extractor) and `get_current_user_id_ws` (WebSocket query string extractor). Eliminated JWT decoding and exception duplication.

**[0004.14]** Prompt: *Architecture review: Explain purpose of `models.py` here.*
- **User Observation**: Pointed out that placing `Message` inside `shared/models.py` violates Vertical Slice Architecture (ADR-0001).
- **AI Action**: Concurred with the user. Removed `Message` from `backend/app/shared/models.py` and placed it into its proper vertical home: `backend/app/chat/models.py`. Updated `backend/alembic/env.py` to import models from `app.chat.models`.

**[0004.15]** Prompt: *Explain lines 93-end in router.*
- **AI Action**: Detailed the WebSocket endpoint `/ws`:
  - Query parameter extraction: `token: str = Query(...)`.
  - Authentication: Validated via `get_current_user_id_ws(token)`. If invalid, calls `websocket.close(code=status.WS_1008_POLICY_VIOLATION)` before accepting.
  - Acceptance: `await ws_manager.connect(user_id, websocket)`.
  - Lifecycle loop: Listens for incoming client frames (`receive_text()`). Ignores unknown frames or ping heartbeats.
  - Teardown: On `WebSocketDisconnect`, reliably invokes `ws_manager.disconnect(user_id, websocket)` to prevent socket leaks.

**[0004.16]** Prompt: *Explain private helper methods in `service.py`: purpose and problems they solve.*
- **AI Action**: Analyzed service design:
  - `_assert_participant`: Enforces authorization and prevents Insecure Direct Object References (IDOR). Verifies the requesting user is either `user1_id` or `user2_id` of the match, raising `403 Forbidden` otherwise. Returns partner ID for target WebSocket event delivery.
  - `_encode_cursor` / `_decode_cursor`: Serializes and deserializes `(created_at, message_id)` into opaque, URL-safe Base64 strings. Prevents leaking database implementation details or raw timestamps to the client, preventing SQL syntax errors and URL parameter tampering.

**[0004.17]** Prompt: *Explain why `IntegrityError` occurs on send and why `is_new` flag is needed.*
- **AI Action**: Detailed idempotency handling:
  - If a client sends a message, loses network connectivity before receiving the 201 response, and retries the HTTP request with the identical `client_message_id`, the unique constraint `(match_id, sender_id, client_message_id)` triggers a PostgreSQL `IntegrityError`.
  - Catching `IntegrityError` rolls back the duplicate insert and fetches the already-existing record from the database.
  - Setting `is_new = False` on recovered duplicates ensures the existing message is returned to the client idempotently without broadcasting a second duplicate `"new_message"` WebSocket notification to the recipient.

**[0004.18]** Prompt: *Give an example request with cursor parameter.*
- **AI Action**: Provided concrete example:
  - Initial fetch: `GET /chat/3662690a-34f0-44fb-a94c-d9596f9a4484/messages?limit=20`.
  - Response includes `next_cursor: "MjAyNi0xMC0xMlQxNDoyMzo0NS4xMjM0NTYrMDA6MDAjM2Y0..."`.
  - Subsequent fetch: `GET /chat/3662690a-34f0-44fb-a94c-d9596f9a4484/messages?cursor=MjAyNi0xMC0xMlQxNDoyMzo0NS4xMjM0NTYrMDA6MDAjM2Y0...&limit=20`.

**[0004.19]** Prompt: *Explain `get_messages_page` mechanism and ID comparison in Rule B.*
- **AI Action**: Explained SQL keyset pagination mathematics:
  - Messages sorted descending: `ORDER BY created_at DESC, id DESC`.
  - Paginating backwards requires fetching items where `(created_at, id) < (cursor_created_at, cursor_id)`.
  - Expanded into boolean logic:
    - Rule A: `created_at < cursor_created_at` (message is strictly older).
    - Rule B: `(created_at == cursor_created_at) AND (id < cursor_id)` (message has identical microsecond timestamp, broken by UUID tie-breaker).
  - Uses index `ix_messages_match_created_at_id` without `OFFSET` scans, guaranteeing $O(1)$ performance regardless of conversation depth.

**[0004.20]** Prompt: *Verify step 3 is done.*
- **AI Action**: Verified Chat slice backend:
  - Models, schemas, repository, service, and router all in place.
  - Router mounted in `main.py`.
  - Verified with `make lint` (50 files checked, 0 errors).

**[0004.21]** Prompt: *Proceed to step 4.*
- **AI Action**: Initiated frontend API and WebSocket hook integration.

**[0004.22]** Prompt: *Explain current frontend architecture and React hook concept.*
- **AI Action**: Provided architectural overview:
  - Architecture: Vite + React 19 SPA, CSS Modules for scoped styling, centralized REST client with `fetch`, JWT stored in `localStorage`.
  - What is a Hook: Reusable function encapsulating stateful logic and side effects (`useState`, `useEffect`, `useCallback`, `useRef`). Enables components to tap into React primitives without class hierarchies.

**[0004.23]** Prompt: *Confirm readiness for Step 4 completion.*
- **AI Action**: Completed `frontend/src/api/client.ts` update (returning `undefined` on 204), `frontend/src/api/chat.ts`, and `frontend/src/hooks/useWebSocket.ts`. Verified with `npm run lint`.

**[0004.24]** Prompt: *Proceed to Step 5 (Chat UI).*
- **AI Action**: Built `frontend/src/pages/Chat.tsx` and `Chat.module.css`:
  - Split message bubbles (`mine` vs `theirs`) via token `sub` claim.
  - Real-time updates via `useWebSocket`.
  - In-place message edit and delete controls.
  - In-conversation substring search bar.
  - Keyset pagination with "Load older messages" button.
  - Updated `frontend/src/pages/Matches.tsx` to link to `/chat/:matchId`.
  - Registered route `/chat/:matchId` in `frontend/src/App.tsx`. Verified with `npm run lint` and `npm run build`.

**[0004.25]** Prompt: *Summarize step 5 changes.*
- **AI Action**: Provided comprehensive recap of frontend changes:
  - Added full message bubble layout with timestamps and sender attribution.
  - Connected live WebSocket message receiver to update list in real time.
  - Implemented search input filtering messages through backend endpoint.
  - Hooked up edit and delete controls with hard-delete semantics (ADR-0012).
  - Verified TypeScript builds cleanly with `npm run build`.

**[0004.26]** Prompt: *Debugging signup error: `column "location_label" of relation "users" does not exist`.*
- **AI Action**: Diagnosed runtime error from FastAPI stack trace:
  - Identified that recent profile commits introduced `location_label` and `photo_key` migrations (`4cf7f321e10c`, `2b671d9baec2`, `54f977295630`) that were not yet applied to the database.
  - Ran `uv run alembic upgrade head` to bring schema up to date.

**[0004.27]** Prompt: *No matches currently, can I artificially create them for test purposes?*
- **AI Action**: Explained how to generate test matches:
  - Created test account `alex@example.com` (`password123`) alongside `kylian@mbappe.fr.com`.
  - Executed database script inserting reciprocal swipes and mutual match record (`3662690a-34f0-44fb-a94c-d9596f9a4484`).

**[0004.28]** Prompt: *It works, wow. How to test lazy loading? What are the limits right now? Send creds of those two users.*
- **AI Action**: Clarified limits and provided testing utilities:
  - Pagination boundary is 20 messages per page.
  - Provided script to seed 25 sequential messages into match `3662690a-34f0-44fb-a94c-d9596f9a4484`.
  - Sent credentials for `alex@example.com` (`password123`) and `kylian@mbappe.fr.com`.

**[0004.29]** Prompt: *Bug fix — Lazy loading scroll UX bug.*
- **Issue**: Clicking "Load older messages" caused the chat window to jump back down to the bottom of the conversation due to an effect triggering `scrollIntoView()` on message count change.
- **Resolution**: Removed the blanket message count effect. Implemented synchronous scroll position preservation in `useLayoutEffect`: measured `container.scrollHeight` before prepending older messages, and adjusted `scrollTop += (newScrollHeight - prevScrollHeight)` before browser paint. Auto-scroll to bottom restricted to initial load, user-initiated sends, and incoming messages when already near bottom.

**[0004.30]** Prompt: *Compact conversation into `ai/prompts`, omit anything irrelevant to labs, try to keep as many details as possible.*
- **AI Action**: Generated prompt record in `ai/prompts/0004-chat-and-websockets-implementation.md` detailing all architectural, engineering, and debugging steps from the session.
