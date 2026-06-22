---
description: Start a new Goals-managed goal and begin its first phase.
argument-hint: <objective>
---

Start a durable, reviewable goal for: **$ARGUMENTS**

1. Run `goals start "$ARGUMENTS" --agent claude`. On `main`/`master` this creates
   an isolated worktree (it prints the path); on a feature branch it may work
   in place. **Do all work for this goal in the path it printed** — if it created
   a worktree, run commands and edit files there; the user never has to `cd`.
2. **Pause + Assess the goal first** (PACERS — see `/goals-problem-solving`).
   Rephrase "$ARGUMENTS" into a specific, testable problem; ask *why* until it
   simplifies to the root; let the sub-problems become the phases. Record the
   goal-level breakdown so the user can trace the framing:
   `goals assess breakdown --file breakdown.json` (problem, whys, sub-problems).
   Skip only if the goal is trivial and unambiguous.
3. Run `goals next --agent claude` (from that path) and follow the phase loop it
   prints: work only the current phase, then record evidence with
   `goals phase evidence <PHASE> --file <evidence.json>`, run
   `goals phase review <PHASE>`, and once it passes, `goals phase accept <PHASE>`.
3. Before interrupting the user, run `goals check` (or `goals brief`) and ask in
   its plain wording only if it says you're waiting on the user.

Keep going phase by phase until `goals check` reports the goal complete. Use
`/goals:check` anytime for status and `/goals:diagram` to visualize it.

**When the goal completes** (optional, recommended if it was painful, stalled, or
complex): offer to run `/goals:critique` — a retrospective that records durable
lessons to memory and surfaces cross-goal patterns. Skip it for a trivial,
first-try-clean goal.

**Keep the goal pinned.** End every turn while this goal is active with a short
pin block, so the dashboard link and status are always the last thing on screen.
Pull the values from the latest `goals check` output (re-run it if unsure — it's
read-only) and never invent them. Keep it to ~4 lines:

```
---
📌 **<goal objective>** · Phase <current>/<total> (<n> accepted)
Waiting on: <"you — <one-line ask>" or "nothing — agent is working">
Dashboard: <file:// link from goals check, click to open>   ·   Next: `goals next --agent claude`
```
