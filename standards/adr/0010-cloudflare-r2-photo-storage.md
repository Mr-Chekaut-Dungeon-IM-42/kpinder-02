# Cloudflare R2 for profile photo storage

- Status: accepted
- Date: 2026-10-08

## Context

`POST /auth/profile/photo` (spec.md §3) validates an uploaded photo (content-type/magic bytes, size) and needs somewhere durable to put the file, then stores a `photo_url` on `User` pointing at it. The spec as written said "a local disk volume under a randomized UUID filename" — but `spec.md` §5 also commits to Railway for staging, auto-deploying on every merge to `main`. A container filesystem on a PaaS like Railway is not durable across redeploys/restarts (no persistent volume is provisioned for the backend service), so a locally-stored photo would be silently lost the next time the service redeploys — which happens on every merge to `main`. Some actually-durable object storage is needed, reachable from both local dev and the hosted backend.

## Decision

Store uploaded profile photos in Cloudflare R2 (free tier). `POST /auth/profile/photo` uploads the validated file to a dedicated R2 bucket under a randomized UUID object key (same naming scheme the original local-disk design used, just a different destination), then stores the resulting public object URL as `User.photo_url`. R2 credentials (account ID, access key ID/secret, bucket name) are read via `pydantic-settings` like every other secret (spec.md §5) — never committed, `.env.example` only.

## Alternatives considered

- **Local disk volume (the original spec.md wording)** — zero external dependency, simplest to implement and test locally. Rejected for the reason in Context: it doesn't survive a Railway redeploy, which happens on every merge to `main` — this isn't a hypothetical edge case, it's the project's own documented deploy trigger. Would work for local dev only, which isn't where photos need to persist.
- **AWS S3** — the default/familiar object-storage choice, same API shape R2 was designed to be compatible with. Rejected in favor of R2 specifically because R2's free tier has no egress fees (S3 charges for data transfer out, which matters for serving photos to clients) and the course project has no budget — R2's S3-compatible API means this choice costs nothing in implementation complexity relative to S3 while being free to actually run.
- **Database BLOB column (storing photo bytes directly in Postgres)** — no second infra dependency at all. Rejected: bloats `User` rows and every query that touches them (including the candidate-ranking query in `matching`, which already reads `User` directly per ADR-0002), and turns a static-asset-serving problem into a database-performance problem for no benefit.

## Consequences

Introduces a second external dependency beyond Postgres (an R2 bucket + API token), which must be provisioned in every environment that needs to serve/accept photos (local dev needs real or mocked R2 credentials; CI's integration tests either need a reachable test bucket or must mock the upload client). `POST /auth/profile/photo`'s failure modes now include "R2 unreachable/credentials invalid" in addition to the existing content-type/size validation failures — the same DB/source-failure-handling pattern (spec.md §3: generic `503`, no leaking the underlying error) extends to this call. Local dev loses the "it just works with zero setup" property a disk volume had, in exchange for actually matching what happens in the deployed environment.
