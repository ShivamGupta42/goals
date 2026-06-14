---
description: Advance the active goal — work the current phase and record evidence.
---

Advance the active Goals goal.

1. Run `goals next --agent claude` and read the current phase, its goal, and
   acceptance criteria. Work **only** the current phase.
2. Make the change, then record proof: write an evidence JSON and run
   `goals phase evidence <PHASE> --file <evidence.json>` (changed files, checks
   run, acceptance met, known gaps, confidence).
3. Run `goals phase review <PHASE>`; fix anything it flags; when it passes, run
   `goals phase accept <PHASE>`.
4. Run `goals check`. If it says you're waiting on the user, ask one
   plain-language question using its wording and stop. Otherwise continue to the
   next phase.

End every turn with the goal pin (~4 lines), sourced from `goals check`, so the
dashboard link and status stay on screen:

```
---
📌 **<goal objective>** · Phase <current>/<total> (<n> accepted)
Waiting on: <"you — <one-line ask>" or "nothing — agent is working">
Dashboard: <file:// link from goals check, click to open>   ·   Next: `goals next --agent claude`
```
