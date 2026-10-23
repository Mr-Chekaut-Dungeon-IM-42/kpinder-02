# Centralized SQLAlchemy models in shared core

- Status: accepted
- Date: 2026-10-15
- Amends: [ADR-0001](0001-vertical-slices-over-layered.md), [ADR-0002](0002-shared-core-boundary.md)

## Context

Originally, ADR-0001 established vertical slices (`auth`, `matching`, `chat`), intending each slice to own its own router, service, repository, and models (`models.py`). However, ADR-0002 placed core user models (`User`, `Interest`, `UserInterest`) into `app/shared/` because other slices needed to reference user profiles.

Over time, this created an architectural inconsistency:
- Some models lived in `app/shared/models.py` (`User`, `Interest`, `UserInterest`).
- Other models lived in slice-specific `models.py` (`Swipe` and `Match` in `matching`, `Message` in `chat`).

During the Lab-3 project defense, the teacher identified this split as an anti-pattern:
> *"models повинно бути в shared або у кожному слайсі"*

Having a partial split caused significant issues:
1. **Foreign key & ORM relationship coupling**: `Swipe`, `Match`, and `Message` all have foreign keys to `User.id`. Splitting them across slice directories led to circular import hazards and complex Alembic target metadata imports.
2. **Pull conflicts and drift**: Synchronization drift occurred when shared models were updated or re-imported across slice boundaries.
3. **Cognitive overhead**: Developers had to guess whether a model was considered "shared" or "slice-private".

## Decision

Consolidate all SQLAlchemy declarative ORM models into a single canonical module: [`backend/app/shared/models.py`](../../backend/app/shared/models.py).
Permanently remove all slice-level `models.py` files (`auth/models.py`, `matching/models.py`, `chat/models.py`).

1. **Single Source of Truth**:
   - `app.shared.models` defines `Base`, `User`, `Interest`, `UserInterest`, `Swipe`, `Match`, and `Message`.
   - All repositories, CQRS command/query handlers, Alembic migrations (`alembic/env.py`), and test fixtures import models strictly from `app.shared.models`.
2. **Slice Autonomy Preserved via Behavior**:
   - Slices continue to independently own their business logic, CQRS commands, queries, repositories, and API routers.
   - Slices do not import business logic from each other. They interact with data strictly through their own repositories and shared models.

## Relationship to Previous ADRs

- **[ADR-0001](0001-vertical-slices-over-layered.md)**: Partially rewritten/amended. ADR-0001 stated that each slice owns its own `models.py`. This statement is superseded: slices own their routers, commands, queries, and repositories, but all relational database models reside in `app.shared.models`.
- **[ADR-0002](0002-shared-core-boundary.md)**: Extended. ADR-0002 permitted `shared/` to hold core user models; this decision expands `shared/models.py` to hold all application models (`Swipe`, `Match`, `Message`).

## Alternatives considered

- **Per-slice models with pure separation (separate models in every slice)**:
  Keep `User` in `auth`, `Swipe`/`Match` in `matching`, `Message` in `chat`.
  *Rejected*: In a monolithic relational database, foreign key relationships (`Match.user_a_id -> users.id`, `Message.match_id -> matches.id`) require SQLAlchemy `ForeignKey` and Alembic to discover all tables. Separating them leads to circular imports or string-based reflection hacks, creating unnecessary complexity without the isolation benefits of microservices.
- **Horizontal layering split**:
  Reverting the entire codebase to horizontal layers (`controllers/`, `services/`, `repositories/`).
  *Rejected*: Vertical slices remain far superior for business logic cohesion and CQRS clarity. Centralizing only the database schema (`models.py`) retains vertical slice independence while giving SQLAlchemy and Alembic a single coherent metadata tree.

## Consequences

- **Consistent architecture**: Resolves defense feedback by eliminating the confusing hybrid model structure.
- **Clean Alembic migrations**: Alembic `env.py` points to a single `from app.shared.models import Base` without needing to import from multiple disparate slice modules.
- **Zero circular imports**: Relationships between `User`, `Match`, and `Message` are declared in a single module without cross-module import tangles.
- **Slice data clarity**: Slices import models from `app.shared.models` while keeping their queries and commands strictly within their slice boundaries.
