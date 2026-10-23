# Conventional Commits enforced on PR title, with squash-merge

- Status: accepted
- Date: 2026-10-16

## Context

The task requires CI to enforce the Conventional Commits format and block merge otherwise. What actually needs linting depends on the merge strategy: with a merge commit, every individual commit in the PR lands on `main`'s history, so each one would need to conform; with squash-merge, GitHub collapses the PR into a single commit using the PR title (plus an optional body) as the message, so only that one string needs to conform.

## Decision

PRs into `main` are **squash-merged**, and CI enforces Conventional Commits format on the **PR title only** (e.g. via a PR-title-linting GitHub Action), not on every intermediate commit a contributor pushes while working on the branch.

## Alternatives considered

- **Merge commit + lint every commit** (e.g. `commitlint` over the PR's commit range): keeps full commit-by-commit history on `main` and forces clean conventional commits the entire way through a branch's life, not just at the final title. Rejected for this project: the team already treats a PR's commits as a working log (fixup commits, "wip", review-response commits are normal and useful locally), and retroactively forcing every one of those into Conventional Commits format fights how the branch is actually used day-to-day without adding information `main`'s history needs — the PR title plus its diff already is the unit of review and the unit of history once squashed.
- **Merge commit, lint only the merge commit message**: avoids forcing clean history on in-progress branches, but GitHub's default merge-commit message is a generic "Merge pull request #N" unless manually edited at merge time — enforcing a format there just shifts the discipline from "write a clean PR title" to "remember to edit the merge commit message box," with no real benefit over squash.

## Consequences

- `main`'s history is one commit per PR, titled in Conventional Commits format — readable as a changelog directly, and this is what any future changelog-generation tooling (if added) would consume.
- Contributors are free to commit however they like on a branch (including "wip", "fixup", non-conventional messages) — only the PR title is checked, and it's checked on every push to the PR so it can be fixed before merge without rewriting history.
- If the project ever wants per-commit traceability preserved on `main` (e.g. to `git bisect` by individual logical change rather than by PR), squash-merge works against that — revisiting this ADR would be the right move at that point, not quietly switching merge strategies.
