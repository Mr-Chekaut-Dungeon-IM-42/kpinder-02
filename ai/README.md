# AI trail

Full prompt trail for every AI-assisted design/implementation session, plus a self-audit of where the AI's output cut corners.

## Structure

- `prompts/NNNN-slug.md` — one file per session, numbered sequentially. Each file is a condensed but faithful log of the session: every user prompt, and the AI's key recommendation or action in response, numbered as `[NNNN.k]` so the audit can link to a specific exchange.
- `audit.md` — top-3 (per session, or per project phase) places where the AI's recommendation was the simpler/weaker option and had to be corrected. Each entry links: the prompt (`prompts/NNNN-slug.md#NNNN.k`), the feedback comment (what the human actually said), and the additional spec (where `spec.md` was changed as a result).

## Why top-3, not exhaustive

The point isn't to catalog every accepted recommendation — it's to show the discrepancies: the cases where the AI defaulted toward a simpler/safer answer and a human had to push back for the project's actual needs. An exhaustive log of agreements is noise; the corrections are the signal.

## Convention for new sessions

1. Start a new `prompts/NNNN-slug.md` file for each distinct working session (e.g. a `/grill-me` run, a feature-implementation session).
2. After the session, review it for corner-cutting: recommendations that optimized for "simple to implement" or "fewer dependencies" over what the project actually needed, and that only got corrected because a human caught it.
3. Add the top-3 (or fewer, if fewer are found) to `audit.md`, following the existing entry format.
