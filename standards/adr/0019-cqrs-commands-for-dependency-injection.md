# CQRS command handlers for dependency injection and business logic

- Status: accepted
- Date: 2026-10-15

## Context

The backend was originally organized as functional services and repositories where every function accepted infrastructure dependencies (such as `db: AsyncSession`, `ws: ConnectionManager`, `storage: PhotoStorage`) as its first arguments:

```python
async def send_message(db: AsyncSession, caller_id: UUID, match_id: UUID, data: MessageSendRequest):
    ...
```

As the application grows, this procedural approach leads to **parameter drilling** (threading 3–5 infrastructure arguments through routers, services, and repositories). Furthermore, unit testing procedural functions requires monkey-patching module-level dependencies using `unittest.mock.patch("app.<slice>.service.repository.<func>", ...)`, making test suites brittle to internal refactoring.

During the Lab-3 defense, this architectural tension was identified: as resources expand, developers spend excessive effort manually wiring dependencies across functional signatures. We evaluated alternative dependency management and decoupling strategies.

## Decision

Adopt **CQRS (Command Query Responsibility Segregation)** with explicit **Command and Query Handlers** across all vertical slices:

1. **Commands (Writes / State Mutations)**:
   - Each state-altering use case is represented by a dedicated Command class (e.g. `SendMessageCommand`, `SwipeCommand`, `SignupCommand`).
   - Infrastructure dependencies (`db: AsyncSession`, `ws: ConnectionManager`, `storage: PhotoStorage`) are injected via the class constructor `__init__`.
   - Business inputs (`caller_id`, payloads, IDs) are passed to the asynchronous `execute(...)` method.
   - Commands own transaction boundaries, business invariant validation, and side-effects (such as real-time WebSocket notifications).

2. **Queries (Reads / Projections)**:
   - Each read operation is represented by a dedicated Query class (e.g. `GetMessagesQuery`, `GetFeedQuery`, `GetMatchesQuery`).
   - Queries depend solely on read-capable infrastructure (such as the database session) and return validated response schemas without side-effects.

3. **FastAPI Wiring**:
   - Command and Query instances are wired into FastAPI endpoint handlers using native FastAPI `Depends(...)` factory functions (e.g., `cmd: SendMessageCommand = Depends(get_send_message_command)`).

4. **Testing Ergonomics**:
   - In unit tests, command and query handlers are instantiated directly with mock dependencies (`cmd = SendMessageCommand(db=mock_db, ws=mock_ws)`). This eliminates global string-based monkey patching (`patch("...")`).

## Alternatives considered

- **Procedural services with ambient context (`contextvars` / task-local storage)**:
  Storing the database session and current user in Python `contextvars` eliminates parameter passing, but introduces implicit global state. If a function is called outside an active HTTP request context (e.g., background tasks, mutmut workers, or unit tests without context fixtures), it fails at runtime. It also hides the dependency graph from static type checkers.
- **Runtime DI decorators (`@inject` / `fast-depends` / `injector`)**:
  Decorating standalone functions to inject dependencies at runtime via reflection. Rejected because it adds external framework magic, obscures stack traces, and confuses static linters/type checkers (Ruff/Pyright).
- **Monolithic Service Classes (e.g., one `ChatService` class holding all chat methods)**:
  Groups all methods for a slice into a single class. Rejected because it violates the Single Responsibility Principle: a monolithic service class gathers all dependencies required by *any* method in the slice into a single bloated `__init__`, even when an individual endpoint only needs a small subset.

## Consequences

- **Explicit dependency graph**: Every use case explicitly declares exactly the dependencies it requires in its `__init__`.
- **Pure, patch-free unit testing**: Tests pass mocked dependencies directly into constructors, making tests robust against refactoring and internal renaming.
- **Clear Separation of Concerns**: Mutation logic and read projections are cleanly isolated.
- **More files / classes**: Each use case is an explicit class. For small slices, this increases file count compared to a single procedural file, but improves readability, maintainability, and testability.
