# Dogfood findings — 3 small projects through goals + PACERS

I built 3 real projects end-to-end with the framework and watched where a
**non-technical** and a **technical** user would each get stuck.

| # | Project | Audience lens | Outcome |
|---|---|---|---|
| 1 | `tip-split` — a CLI that divides a bill by N people, tip included | tech | built, journey populated, dashboard rendered |
| 2 | `focus-timer` — a single self-contained HTML countdown page | non-tech | built `--in-place`, audience toggle exercised |
| 3 | `quote` — a tiny script that prints a random quote | hobbyist | built, assumption recorded |

What worked well: `goals check` / `goals brief` are genuinely plain-language and
calm ("Nothing important needs your answer", "Next safe step"). The new
`assess assume` flags are pleasant. The audience toggle on assumptions works
(High school stays clean; Hobbyist appends the "it's one .html file" framing).

---

## Issues, tagged by who hits them

### Fixed in this PR
- **[both] PACERS Assess wasn't wired into the CLI handoff.** `goals next` listed
  14 steps but never told the agent to record assumptions or a breakdown — that
  lived only in the Claude `.md` skill. A CLI/Codex-driven agent therefore never
  populated the journey. → Added an explicit Assess step to the handoff loop.

### Strengthen (proposed — your call)

1. **[non-tech] The audience toggle only reframes assumptions, not the breakdown.**
   At "High school", the breakdown still shows `argparse interface`, `round to
   cents`, `Compute each share = (bill*(1+tip))/people`. The toggle sets the
   expectation "make it all simpler", but the most jargon-dense part doesn't
   change. Options: (a) give `ProblemBreakdown`/`Subproblem` optional
   `audience_notes` too; (b) scope the toggle label to "what the agent assumed"
   so it doesn't over-promise; (c) enforce plain breakdown text via authoring
   guidance only. (a) completes the promise; (b) is the 5-minute honest fix.

2. **[non-tech] `goals next` is a wall of text.** ~15 numbered steps + a parallel-
   worktree gate + recommended checks + permission policy + memory — for a
   *tiny* goal. The full 60–130-char absolute path is repeated ~8 times. A
   non-tech user freezes; a tech user skims and ignores most of it. Proposed: a
   short default handoff (objective, current phase, 3 commands) with `--full`
   for the exhaustive version; print paths relative to the worktree.

3. **[both] The worktree name is a 61-char slug of the objective.**
   `p1-tipsplit-build-a-tiny-tip-split-cli-that-divides-a-bill-b` (truncated
   mid-word). It's created as a *sibling* of where you ran `start`, so your work
   lives in a differently-named folder next door. Proposed: cap the slug to ~3–4
   words + short id (`tip-split-7a3f`), and say plainly where it went.

4. **[both] `--in-place` is the friendlier path but isn't the default.** On
   `main`, `start` silently creates the worktree monster. `--in-place` prints
   "Working in place … (no cd needed)" — much calmer. Proposed: when the repo is
   clean and the user didn't ask for parallelism, default to in-place (or ask
   once in plain words).

5. **[non-tech] `assess breakdown` requires hand-written JSON.** `assume` has
   nice flags; `breakdown` needs a nested JSON file a non-tech user can't author
   and a tech user finds tedious. Proposed: a flag/REPL form, or let the agent
   derive the breakdown from recorded assumptions.

6. **[both] First contact is agent-centric + command sprawl.** `--help` opens
   with "Goals helps AI **agents** finish bigger tasks" and lists ~25 commands
   across 4 panels; `start` vs `create` is ambiguous. Proposed: a one-line "new
   here? run `goals start \"...\"`" and demote the building-blocks.

---

## The one-line version
The framework's *plain-language* surfaces (`check`, `brief`, the dashboard
journey) are strong. The *workflow* surfaces (`next` handoff, worktree naming,
breakdown authoring) are still built for an expert agent, not a person — and the
audience toggle, the headline non-tech feature, stops halfway (assumptions yes,
breakdown no). Closing #1, #2, and #4 would do the most for non-tech users; #3
and #5 most for tech users.
