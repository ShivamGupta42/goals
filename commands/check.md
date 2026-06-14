---
description: Show the active goal's status, proof, and what needs the user.
---

Run `goals check` and summarize for the user in plain language: the current
phase, progress (steps accepted), what proof exists, and anything under
"Needs The User." If something needs the user, surface it as one clear question
using the brief's wording. Otherwise state the next safe step you'll take.

End with the goal pin (~4 lines), sourced from the same `goals check` output, so
the dashboard link and status stay on screen:

```
---
📌 **<goal objective>** · Phase <current>/<total> (<n> accepted)
Waiting on: <"you — <one-line ask>" or "nothing — agent is working">
Dashboard: <file:// link from goals check, click to open>   ·   Next: `goals next --agent claude`
```
