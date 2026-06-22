---
name: goals-critique
description: Run a retrospective on a completed (or stalled) Goals goal to learn from it — critique both the engine/UX friction the CLI created AND the agent's own execution quality, record durable lessons into self-evolution memory, surface cross-goal patterns, and file engine friction upstream. Use after `goals check` reports a goal complete, after a painful or stalled goal, or periodically to learn across every goal you run.
---

# Goals Critique — learn from every goal you run

Ships with the Goals CLI. Run it **after a goal completes or stalls**, from that
goal's worktree. It turns one goal's experience into durable behavior change via
`goals memory`, and turns friction that repeats across runs into upstream fixes.

It is **orthogonal to `goals loop improve`**: that tunes reusable *loop-design
templates*; this critiques the *agent experience and execution* of a real goal.

## Two lenses (keep them separate)

Every finding is one of two kinds. Don't blur them — they have different fixes.

1. **Engine / UX friction** — where the Goals CLI itself slowed you: unclear
   schema, raw errors, surprising gates, missing machine-readable output. Fix =
   an upstream issue/PR against the Goals project, plus a `memory record` so you
   avoid the trap next time.
2. **Agent-execution friction** — where *you* were wrong or wasteful: authored
   invalid evidence without checking the schema, mis-scoped an assumption, skipped
   a cheaper path. Fix = a `memory record --kind learning` that changes your next run.

A finding that's "the tool should have told me" is usually **both**: file it
upstream *and* record the workaround.

## Workflow

**1. Gather the trace.** From the goal worktree:
```bash
goals check            # final status, blocking signals, merge readiness
goals view             # phases + acceptance
goals assess journey   # the recorded breakdowns + assumptions (your reasoning)
goals lineage          # phase-by-phase event history (look for failed reviews / re-records)
```
Note every **failed `goals phase review`**, every evidence re-record, every
assumption you flipped, and any checkpoint you waived — those are where friction lived.

**2. Auto-absorb the obvious.** Let the engine pull gaps, blockers, failed
reviews, and learnings into memory automatically:
```bash
goals memory absorb
```

**3. Critique across both lenses.** For each friction point, write: what happened,
which lens, the root cause, and the concrete next-time change. Be specific and
honest — "I authored evidence with a `summary` field the schema forbids, got a raw
pydantic error, and only fixed it by reading models.py" beats "evidence was hard."

**4. Record durable lessons.** One `memory record` per reusable lesson (skip
one-offs):
```bash
goals memory record "Author phase evidence to the exact Evidence schema (no extra keys); run a 1-line check before submitting." \
  --area gate --kind learning --severity medium --phase P1
```
Use `--kind friction` for things that hurt, `--kind success` for what worked and
should be repeated, `--area` ∈ {phase, skill, gate, decision, docs, test}.

**5. Surface cross-goal patterns** (the "learn from all goals" payoff):
```bash
goals memory suggest --json              # this project: repeated friction → suggestions
goals memory sync <other-goal-root>      # dry-run import of sanitized lessons from another project (add --apply to enact)
```
Anything that recurs across ≥2 goal runs is no longer a one-off — promote it: either a
new/updated skill (durable behavior change) or an upstream engine issue.

**6. Produce `CRITIQUE.md`** in the goal worktree with five sections: **What went
well** · **Engine/UX friction** (each → upstream action) · **Agent-execution
friction** (each → memory id) · **Root causes** · **Next-time changes**. Keep it
scannable; link memory ids and issue links.

**7. File engine friction upstream — opt-in only.** Engine/UX findings are about
the Goals *product*, so they're valuable to every user. But this skill runs on
other people's machines: **never file silently.** The flow:

- **Default = local only.** `CRITIQUE.md` is always written; nothing leaves the
  machine without an explicit yes.
- **Find the repo.** Read the plugin's `homepage` from `.claude-plugin/plugin.json`
  (currently `https://github.com/ShivamGupta42/goals`). If you can't resolve a repo
  or `gh` isn't authenticated, stop at local and tell the user.
- **Sanitize.** Only the *engine/UX* findings go upstream — file:line + the symptom
  + a concrete fix. **Strip all goal content** (objective text, your notes, paths
  outside the Goals source). A maintainer must learn nothing private from the issue.
- **Dedupe.** Before filing, `gh issue list --repo <repo> --search "<symptom>" --state all`
  — if it already exists, link it in `CRITIQUE.md` instead of opening a duplicate.
- **Issue by default; PR only for mechanical fixes.** Open a `gh issue create`
  (label `agent-friction`) per novel finding. Open a PR only when the fix is a
  one-or-two-line mechanical change AND the user explicitly opts into a PR.
- **Show, then ask.** Print the sanitized issue body and ask "file this upstream?"
  per finding (or batch). Record what was filed (with links) back into `CRITIQUE.md`.

## Quality bar

- Cite **file:line or event** for engine claims — a critique that can't point at
  the code is an opinion, not a finding.
- Every recorded lesson must be **actionable next run**, not a description of the past.
- Separate **the tool's fault** from **my fault** explicitly; sycophantic
  "the tool was great" or self-flagellating "I'm bad" both waste the retro.

## When NOT to use
A trivial one-phase goal that passed cleanly on the first try has nothing to teach
— skip it. Run this when a goal was painful, stalled, complex, or when you want to
mine patterns across the goal runs you've accumulated.

See `references/example-critique-thinking-gym.md` for a full worked critique.
