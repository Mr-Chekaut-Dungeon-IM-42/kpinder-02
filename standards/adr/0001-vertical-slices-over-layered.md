# Vertical slices over horizontal layers

- Status: accepted (partially amended by [ADR-0020](0020-centralized-models-in-shared.md))
- Date: 2026-10-02

> **Notice (2026-10-15)**: The statement that slices own their own `models.py` has been amended by [ADR-0020](0020-centralized-models-in-shared.md). All SQLAlchemy models are centralized in `app.shared.models` to eliminate cross-slice model splitting and relationship circularities. Slices own their routers, CQRS commands/queries, and repositories.

## Context

The backend needs an organizing principle. The two live options for a FastAPI + SQLAlchemy monorepo are horizontal layering (a single `routers/`, `models/`, `services/` spanning every feature) or vertical slices (one bounded context per feature, each owning its own router/service/repository/models).

## Decision

Organize the backend as vertical slices — `auth`, `matching`, `chat` — each a self-contained module. A slice owns its router, service, repository, and (where applicable) its own tables. Slices never import another slice's router or service.

## Alternatives considered

Horizontal layering was the default/familiar option, but it was rejected: with three features that have genuinely different lifecycles and data needs, a single `models.py`/`routers.py` spanning all of them would grow into an unreadable pile, and "which files make up feature X" would stop being answerable by directory listing alone.

## Consequences

Module boundaries are explicit and auditable (the lab's own audit step — "чи структура відповідає spec" — maps directly onto "does each slice's folder match its section in spec.md"). The cost: slices aren't fully independent in practice (matching needs auth's profile data, chat needs matching's match records), which forced the next decision — see ADR-0002.
