# AI output audit — top 3 cut corners

Covers session `prompts/0001-architecture-grilling.md`. These are the three clearest cases where the AI's recommendation optimized for "simpler" or "fewer dependencies" over what the project actually needed, and a human correction was required to get the right answer into the spec.

---

## 1. Defaulting to "fewer dependencies" over fit-for-purpose tooling

**Prompt:** [`0001.6`](prompts/0001-architecture-grilling.md#00016) and [`0001.16`](prompts/0001-architecture-grilling.md#00116)

**AI's output:** Recommended dropping the repository layer ("indirection you don't need yet — you're not swapping ORMs") and, separately, recommended plain `lat`/`lng` columns with Haversine SQL instead of PostGIS ("unnecessary dependency... the audit step is explicitly looking to penalize this"). Both times the AI's stated reasoning was the same pattern: minimize dependency count, justified by appeal to the lab's own "top-3 excess dependency" audit criterion.

**Feedback comment:** *"no, add repo layer as well."* / *"let's use postgis, simple queries and native geo support"*

**Why it was a cut corner:** The AI's logic was internally consistent but applied the audit criterion backwards — "fewer dependencies" is not the same thing as "appropriate dependencies for the problem." A repository layer is exactly the right abstraction once a project commits to vertical slices with their own tests (which this one explicitly did); and PostGIS is the standard, more correct tool for geo-radius queries specifically, not an "excess" one — Haversine-in-SQL would have been the actually weaker choice to defend in a lecturer review, despite having one fewer dependency.

**Additional spec:** `spec.md` §1 (internal layering table includes `repository.py`) and §2 (`PROFILE.location` typed as `geography`, candidate query uses `ST_DWithin`).

---

## 2. Recommending the lower-fidelity option for a core, explicitly-named feature

**Prompt:** [`0001.9`](prompts/0001-architecture-grilling.md#00019)

**AI's output:** Recommended polling over WebSockets for the chat slice, on complexity grounds (connection lifecycle, reconnect logic, registry management).

**Feedback comment:** *"no, we want websockets."*

**Why it was a cut corner:** "Real-time messaging" is one of the three features named explicitly in the project brief, not an incidental detail. Polling satisfies the word "real-time" at low fidelity but misses the point of listing it as a named MVP feature at all — if the brief calls out a specific technical capability by name, defaulting away from it to save implementation effort is optimizing for the AI's delivery cost, not the project's actual goal (here, plausibly: demonstrating the harder, more impressive mechanism to the instructor).

**Additional spec:** `spec.md` §1 (`chat` slice: "1:1 messaging over WebSocket") and §3 ("Messaging (chat)" scenario: WebSocket connection + shared registry push).

---

## 3. Scoping out persistence/durability as a default, without being asked to

**Prompt:** [`0001.11`](prompts/0001-architecture-grilling.md#00111)

**AI's output:** Recommended in-app-only, ephemeral notifications — no `Notification` table, no delivery to offline users — framing persistent notifications as "realistically its own vertical slice worth of work you don't need to take on."

**Feedback comment:** *"we want to have ... persistent/offline notifications (stored in DB, visible next time you log in, maybe push notifications)"*

**Why it was a cut corner:** The brief listed "notifications" as part of the chat feature; the AI interpreted that at the narrowest possible reading (transient in-app toast) rather than the ordinary reading (something a user can come back to). This produced a structurally weaker design — it also walked back the AI's own earlier "it's its own bounded context" instinct once corrected, which is exactly what led to `notifications` becoming its own 4th slice with real persistence and event subscriptions, a more defensible architecture for a course project.

**Additional spec:** `spec.md` §1 (`notifications` slice: "persisted notifications, delivery to online users") and §2 (`NOTIFICATION` entity with `read_at`).

---

## Pattern across all three

In each case the AI defaulted toward the option that was cheaper to specify and justified it using a real-sounding engineering principle (dependency minimalism, incremental complexity, YAGNI) — but misapplied that principle against features the project brief had already named as in-scope. The lesson for future sessions: when a brief explicitly names a capability (PostGIS wasn't named, but "real-time messaging" and "notifications" were), treat "is this in scope" as already answered, and only grill on *how*, not *whether*.
