# Visual Goal-Loop Builder — Goal Prompt

Paste-ready prompt for `goals start` (or Claude `/goal` / Codex). Build in three
independently-useful phases. Dogfood the repo's own primitives throughout.

---

```
GOAL: Build a visual goal-loop builder for this repo, dogfooded with the repo's
own primitives. Terminal-first interactive builder (plain text-based TUI); static
HTML is an EXPORT of the builder, not a second codebase. Ship in three
independently-useful phases.

NON-NEGOTIABLES (apply to every phase):
- Dogfood: run `goals start` for this work first; track every phase against that
  goal. Use `goals phase evidence|review|accept` as you go. The builder must be
  able to reproduce its own goal spec.
- One source of truth: the builder writes the existing portable spec
  (.goals/goal-state.json + .goals/GOAL.md via src/goals/portability.py). The
  static HTML is RENDERED FROM that spec (reuse dashboard.py's read-only ethos),
  never hand-authored in parallel.
- Skills are discovered LIVE, never registered: scan ~/.claude/skills/ and
  ~/.codex/skills/ at runtime and read each SKILL.md frontmatter (name,
  description, trigger). The repo maintains NO registry of skills. (This makes
  registries/*.yml + `goals ecosystem recommend` partly redundant for skills —
  flag as a follow-up, do NOT delete it in this work.)
- Cross-agent portability nudge: when an attached skill exists in ~/.claude/
  skills/ but NOT ~/.codex/skills/, flag it and suggest installing it into
  ~/.codex/skills/ so the loop stays runnable under Codex and Claude alike.
- Extend, don't reinvent: reuse the memory loop (goals memory record/absorb/
  suggest), the decision rule (defer unless blocking → explicit user approval),
  and goals emit. Do NOT add a long-running server or a heavyweight runtime dep.
  Keep cli.py thin.
- Each phase ends green: ruff clean + pytest passing, with tests for every new
  path including edge cases.

PHASE 1 — Visual loop builder (text-based TUI), HTML export
  Build an interactive terminal UI that lets a user compose a goal loop:
  - add / edit / reorder / delete phases (blocks) and their acceptance &
    termination conditions
  - search and attach existing skills/commands, discovered live from
    ~/.claude/skills/ and ~/.codex/skills/ (parse SKILL.md frontmatter); show
    name + description + which agent(s) have it; insert the chosen skill as a
    step reference
  - when an attached skill is missing from ~/.codex/skills/, surface a
    "suggest install → ~/.codex/skills/" hint
  - on save: write a valid portable goal spec, AND export a static HTML
    visualization of the designed loop (phases, conditions, attached skills,
    per-skill agent availability) that opens with no server
  Acceptance (verifiable):
  - A user can build a loop end to end, attach ≥1 skill, define ≥1 termination
    condition, and the written spec round-trips back into `goals` cleanly.
  - Skill discovery reads both dirs; a skill present only in ~/.claude/skills/
    produces the ~/.codex/skills/ install suggestion.
  - The exported HTML renders the same loop and opens standalone.
  - Tests cover: empty loop, a loop with attached skills, reorder, the
    Claude-only-skill install hint, and that the spec the builder writes equals
    what portability.py would validate.

PHASE 2 — Loop evaluation (linter) + opt-in auto-improve
  Add `goals loop check` that analyzes a designed loop and reports P0/P1/P2
  issues with concrete fixes. Detect at minimum: no termination condition;
  vague/untestable acceptance criteria; unreachable or duplicate phases;
  infinite-loop / no-progress risk; a referenced skill not found in either skill
  dir; phases with no evidence requirement.
  Add an opt-in `--fix` that applies only the safe, reversible suggestions and
  records what it changed.
  Acceptance:
  - Each defect class above has a failing-loop fixture the checker flags, and a
    healthy fixture it passes clean.
  - `--fix` is idempotent and never edits a loop that already passes.

PHASE 3 — Per-phase regression detection + self-improvement loop
  Hook into phase acceptance: after a phase runs, detect whether something went
  wrong that warrants improvement and log it WITH EVIDENCE via the memory loop.
  Classify each finding: improve-now (blocking → surface to user) vs defer
  (record, no interruption). Deferred items need explicit user approval before
  they're acted on.
  Add a final OPTIONAL step `goals loop improve` that consumes all accumulated
  suggestions + their evidence and proposes focused improvements — to either the
  task execution OR the loop design itself — applying them only on approval.
  Dogfood: this very builder work must accumulate at least one real
  logged-with-evidence improvement against the Phase-0 goal.
  Acceptance:
  - A simulated failed phase produces an evidence-backed memory record.
  - Blocking vs deferred routing is tested; deferred items do not auto-apply.
  - `goals loop improve` turns recorded suggestions into a concrete, reviewable
    change set and is a no-op when there are no approved suggestions.

OUT OF SCOPE (flag, don't smuggle in): a web server / live multi-user editing;
Mode B autonomous execution of the designed loop; non-Claude/Codex adapters;
deletion of the existing registries/ecosystem commands.
```

---

## Locked decisions

- **Builder UI:** plain text-based terminal UI first; static HTML is rendered as
  an *export* of the same portable spec (one render path, two surfaces).
- **Scope:** phased — builder → evaluator → self-improvement loop.
- **Skill source:** live scan of `~/.claude/skills/` + `~/.codex/skills/` via
  `SKILL.md` frontmatter. No repo-maintained registry.
- **Portability:** always suggest installing an attached skill into
  `~/.codex/skills/` when it's Claude-only.

## Open follow-up (separate decision)

Live skill discovery overlaps the existing `registries/*.yml` +
`goals ecosystem recommend` for skills. Decide later whether to retire the skill
portion of the registry once the builder proves out.
