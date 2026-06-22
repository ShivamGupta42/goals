---
description: Retrospective on a completed or stalled Goals goal — learn from it and optionally file engine friction upstream.
---

Run the **goals-critique** skill on the current goal. This is an *optional final
step* — run it after `goals check` reports the goal complete, or any time a goal
was painful, stalled, or complex.

1. Confirm there's a goal to critique: `goals check` (status + blocking signals)
   and `goals lineage` (look for failed reviews / re-records). If the goal was a
   trivial one-phase clean pass, say so and stop — nothing to learn.
2. Follow the **goals-critique** SKILL.md workflow: gather the trace,
   `goals memory absorb`, critique the two lenses (engine/UX vs agent-execution),
   `goals memory record` each durable lesson, then `goals memory suggest` for
   cross-goal patterns. Write `CRITIQUE.md` in the goal worktree.
3. **Upstream is opt-in.** Engine/UX findings can be filed to the Goals repo, but
   only with the user's explicit OK — show the sanitized findings first and ask.
   Default is local `CRITIQUE.md` only. See the skill's step 7 for the
   sanitize + dedupe + `gh` flow.

End by showing the user: lessons recorded (with memory ids), and — if any —
the engine findings awaiting their decision to file upstream.
