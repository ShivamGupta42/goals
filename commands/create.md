---
description: Start a new Goals-managed goal and begin its first phase.
argument-hint: <objective>
---

Start a durable, reviewable goal for: **$ARGUMENTS**

1. Run `goals start "$ARGUMENTS" --agent claude`. On `main`/`master` this creates
   an isolated worktree (it prints the path); on a feature branch it may work
   in place. **Do all work for this goal in the path it printed** — if it created
   a worktree, run commands and edit files there; the user never has to `cd`.
2. Run `goals next --agent claude` (from that path) and follow the phase loop it
   prints: work only the current phase, then record evidence with
   `goals phase evidence <PHASE> --file <evidence.json>`, run
   `goals phase review <PHASE>`, and once it passes, `goals phase accept <PHASE>`.
3. Before interrupting the user, run `goals check` (or `goals brief`) and ask in
   its plain wording only if it says you're waiting on the user.

Keep going phase by phase until `goals check` reports the goal complete. Use
`/goals:check` anytime for status and `/goals:diagram` to visualize it.
