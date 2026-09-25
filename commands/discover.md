---
description: Phase one — understand what the user really wants (pain, desired feel, unknowns) and get a plain-English "yes" before building.
---

Run the **goals-discovery** skill on the active goal. This is the *first* step of
a goal — do it right after `goals start` and **before** Assess
(`goals-problem-solving`). It exists so the rest of the run is aligned: it's
cheaper to fix a misunderstanding now than after it's built.

1. Confirm there's an active goal: `goals check`. If the goal is trivial and
   unambiguous (a typo, a one-line tweak), say so and skip straight to building —
   Discovery is for open-ended or non-technical work where "what they asked for"
   and "what they want" might differ.
2. Follow the **goals-discovery** SKILL.md flow: start from the user's **pain and
   friction** (not features), draw out the **properties and feel** of a good
   outcome, **name what you don't yet understand** instead of assuming it, reflect
   their goal back in plain English, then lay out the approach with **honest
   pros/cons a non-technical person can weigh** (including doing nothing).
3. Capture it durably as you go, exactly as SKILL.md shows: each desired property
   where the run is held to it (measurable → `goals assess assume --depends --phase P3`;
   a feel only the user can judge → a pending P4 `human_validation` checkpoint — never
   `--depends` on P1, where nothing is built to check yet), the rephrased problem and
   open unknowns as open questions via `goals assess breakdown`, your recommended
   approach via `goals decision record --by agent`, and the alignment question as an
   `understanding` checkpoint that needs the user
   (`goals checkpoint record P1 alignment --kind understanding --status needs_user --needs-user`).
   Write `DISCOVERY.md` next to the goal's dashboard
   (`.agent-workflow/goals/<goal>/`, kept out of git).
4. **Get an explicit yes before building.** Ask plainly: *"Here's what I
   understand and how I'd approach it — is this what you want to build?"* When the
   user confirms, flip the checkpoint to `passed`, record their choice with
   `goals decision record --by user`, and continue to Assess. If they
   correct you, fold it in and re-ask — a "no" here is the most valuable feedback
   in the whole run.

End by showing the user: what you understood (their pain → desired feel), what
you still don't know, the approach with its pros/cons, and the one question that
needs their yes before any building starts.
