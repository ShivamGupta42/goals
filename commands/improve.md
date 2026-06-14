---
description: Turn accumulated, evidence-backed memory into a reviewable change set.
---

Run `goals loop improve` and show the user the proposed improvements (each tagged
execution vs loop-design, with its evidence). These come from regressions logged
across phases. Apply only on the user's approval: `goals loop improve --apply`
enacts only the safe, reversible loop-design fixes; deferred items are never
auto-applied. If there are no approved suggestions, say so — it's a no-op.
