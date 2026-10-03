# PostGIS over plain lat/lng + Haversine

- Status: accepted
- Date: 2026-10-02

## Context

Matching needs to filter candidates by distance. The two options are plain `latitude`/`longitude` float columns with distance computed via the Haversine formula in SQL, or PostGIS's `geography(Point)` type with `ST_DWithin` for the radius filter.

## Decision

Use PostGIS. `Profile.location` is a `geography(Point)` column; the candidate query filters with `ST_DWithin`.

## Alternatives considered

Plain lat/lng + Haversine was the initially proposed option, on the grounds of avoiding an extra Postgres extension dependency. It was rejected: PostGIS is the standard, more correct tool for geo-radius queries specifically — not an "excess" dependency by the lab's own audit criterion, but the *appropriate* one. Defending a hand-rolled Haversine query over PostGIS in a lecturer review would have been the harder position, despite nominally having one fewer dependency.

## Consequences

Requires the PostGIS extension enabled on the Postgres instance (local `docker-compose`, CI's testcontainers image, and the hosted database must all run a PostGIS-enabled Postgres image, not vanilla Postgres). In exchange, the radius filter is a single indexed spatial query instead of hand-rolled trigonometry repeated wherever distance matters.
