# Review & learnings — marketing refresh goal

**Phase P4 deliverable.** Did this solve the actual problem? Expected vs. actual,
and what to carry forward.

## Definition of done — met?

| Done-criterion (from `00-definition-of-done.md`) | Status | Proof |
| --- | --- | --- |
| 1. Gap analysis exists (accurate/stale/missing + edits + missing diagrams) | ✅ | `01-gap-analysis.md`; staleness proven by a zero-match grep across all marketing `.md` files (P2 evidence) |
| 2. ≥4 architecture diagrams, each node traceable to code | ✅ | `02-architecture-diagrams.md` + 4 rendered SVGs; anti-drift checks confirm every module/command/registry exists (P3 evidence) |
| 3. Refreshed, complete launch kit + index; follow-ups flagged | ✅ | `03-launch-kit.md` + `README.md`; copy now covers all 5 omitted features; screen-capture work explicitly flagged |

## Expected vs. actual

- **Expected:** mostly copy the marketing branch. **Actual:** the branch was a
  strong base but *silently stale* — zero of its docs mentioned the five newest
  features, and it had no diagrams. The real work was the delta, exactly as the
  Pause note predicted.
- **Surprise:** the executed-proof gate caught a factual error in my *own* P1
  checks — I assumed an `execution_gate.py` module; it doesn't exist (the logic is
  in `gates.py`). The tool's headline feature corrected its own marketing author.
  That anecdote is itself good launch copy.

## Assumptions — final status

| Assumption | Final | Note |
| --- | --- | --- |
| Marketing branch = source material, not a merge | validated | Worked refreshed outputs in `docs/marketing-refresh/`; nothing destructive |
| Positioning locked to "no-nonsense goal workflow engine" | validated | Consistent across `pyproject` + marketing README; refresh kept the voice |
| Diagrams drawn from code, not prose | validated | Anti-drift checks passed for all modules/commands/registries |
| Hero GIF re-record out of scope | held | Flagged as follow-up; all headless assets delivered |

## Remaining risks / follow-ups (P4.C2)

1. **Screen-capture assets** — hero GIF + dashboard screenshot must be re-recorded
   against current behaviour before launch (`03-launch-kit.md` §I).
2. **SVG → PNG** for the GitHub social preview needs an image tool.
3. **Owner actions** — awesome-list PRs and HN/Reddit/X posts, gated on per-channel
   approval (`goals permission check`).
4. **Drift risk going forward** — these diagrams/claims will stale on the next big
   architecture change. Systemize: add a "refresh `docs/marketing-refresh/` on
   architecture change" note so the kit flags instead of silently aging (mirrors
   how `test_skill_hygiene` keeps CLI examples honest).

## What to systemize

The recurring failure mode is *marketing drifting from code*. The durable fix is
to anchor headline claims and diagrams to verifiable code facts (done here via
executed checks) and treat the marketing kit as a refresh-on-change artifact, not
a write-once one.
