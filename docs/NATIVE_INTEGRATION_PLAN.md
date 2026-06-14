# Native Integration Plan — goals inside Claude Code & Codex

Make `goals` work **from inside** Claude Code and Codex: no copy-paste handoff,
no worktree-`cd` friction, one-step install. The CLI stays as the execution
engine and the local-AI / scripting fallback. **No MCP** — skills + slash
commands + hooks over the CLI (MCP is a deferred, optional surface).

## Locked decisions (from design discussion)

1. **Name:** keep `goals`. Disambiguate from Claude Code's built-in `/goal` via
   plugin command namespacing — `/goals:create`, `/goals:check`, … (a Claude
   Code plugin named `goals` namespaces its commands as `/goals:<cmd>` for free).
2. **Workspace:** **in-place in the current repo by default** — a goal tracks the
   current branch; no forced sibling worktree. Worktrees become opt-in
   (`--worktree`). Existing worktree goals keep working.
3. **Integration:** **skills + slash commands + hooks over the CLI.** MCP
   deferred — everything routes through the CLI, so MCP can be added later as a
   thin extra surface without touching the core.
4. **Install:** one step per agent (`goals setup --agent claude|codex|both`),
   plus a Claude Code plugin marketplace entry.

## Why this shape (stability rationale)

Both skills and MCP are only *invocation surfaces* over the existing `goals` CLI.
Skills add a text file pointing the model at the CLI; MCP adds a long-running
process + a protocol + a second execution path to keep in sync. The CLI is the
stability anchor; skills/commands/hooks are thin, swappable convenience layers.
The loop *automation* comes from command-prompt bodies + hooks, not from hoping
the model picks a skill.

## Current state (what we change)

- `goals start` always creates a sibling worktree (`runtime.create_goal` →
  `require_clean_repo` + `create_worktree`, runtime.py:91/98) and prints a
  paste-the-handoff next-step. Root cause of the "no update" and "wrong
  directory" confusion.
- Already shipped and reused: bundled skills (`goals-decision-explainer`,
  `goals-architecture-map`), live skill discovery, `goals skills install
  --target claude|codex|both`, portable spec (`.goals/`), context sync into
  `AGENTS.md`/`CLAUDE.md` (`portability.sync_context_files`), the Mode A handoff.
- No plugin/command/hook scaffolding exists yet (greenfield for the plugin).
- Some read commands already support `--json`; others need it.

## Target architecture

```
        Claude Code session                 Codex session            Local AI
        ───────────────────                 ─────────────            ────────
  /goals:create  /goals:check          prompts + ~/.codex/skills    goals CLI
        │   (plugin commands)                  │                        │
        ▼                                      ▼                        │
   skills (model-invoked verbs)  ──────────────┘                        │
        │                                                               │
   SessionStart hook  → injects active goal       (CLI is the common ───┘
   Stop hook (opt-in) → enforce phase gate         denominator everywhere)
        │
        ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  goals CLI  (single execution engine; --json everywhere)       │
   │  runtime / gates / portability / memory / dashboard / phases   │
   └──────────────────────────────────────────────────────────────┘
        │
   .agent-workflow/goals/<id>/  (in current repo, in-place)
   .goals/GOAL.md + goal-state.json  (portable, committable)
```

---

## Phase 1 — In-place workspace (foundation)

The change that removes the friction at the root: a goal lives where you are.

**Tasks**
- `create_goal(..., worktree: bool = False)`: when `worktree=False` (new
  default), skip `create_worktree`; set `WorktreeLease(mode="single",
  base_repo=repo, worktree_path=repo, branch=current_branch)` — i.e. attach goal
  tracking to the current repo/branch. State dir stays
  `<repo>/.agent-workflow/goals/<id>`.
- Relax `require_clean_repo` for in-place (you are actively working). If the
  current branch is the default branch (`main`/`master`), emit a gentle note
  ("you're on main; consider a feature branch") — do **not** force one.
- `goals start`: default in-place; add `--worktree` to opt into the old isolated
  behavior; keep `--new` for greenfield projects (greenfield can stay in-place
  in the new repo).
- `start_workflow` / `render_start_workflow`: drop the "cd into worktree → paste
  handoff" framing for in-place; next step becomes "run `/goals:next` (or `goals
  next`) here."
- Back-compat: existing worktree goals load and run unchanged
  (`active_goal_dir` already resolves from the current repo; worktree goals are
  found when you're in the worktree).

**Verify**
- `goals start "x"` in a repo → state in **this** repo; `goals check` works from
  the same directory with no `cd`. (verify: test asserts goal dir == cwd repo)
- `goals start --worktree "y"` → still creates the sibling worktree. (verify:
  test asserts a worktree was created)
- On `main`, `goals start "x"` succeeds with a note, not a refusal. (verify:
  test)
- Existing worktree-goal fixtures still load. (verify: existing tests pass)
- ruff + pytest green.

**Risk:** changing the default is a behavior change. Mitigation: `--worktree`
preserves old behavior; document clearly; existing goals unaffected.

---

## Phase 2 — CLI ergonomics for in-agent use

Make the CLI clean to call from skills/commands/hooks and to parse.

**Tasks**
- Audit read commands (`status`, `check`, `next`, `brief`, `issues`,
  `checkpoint current`, `phase` reads) and add `--json` where missing, returning
  the underlying model dump. (`--json` already exists on several.)
- Add `goals context [--json]`: emit the compact active-goal block for the
  SessionStart hook to inject (objective, current phase, acceptance, waiting-on,
  next safe step). Reuse `portability.render_context_block` / `goals brief`.
- Ensure all commands exit non-zero only on real errors and print the improved
  GoalsError messages (already done on `main`).

**Verify**
- Every read command emits valid JSON under `--json`. (verify: tests parse it)
- `goals context --json` returns the active-goal block; errors cleanly with the
  improved message when no goal exists. (verify: tests)
- ruff + pytest green.

---

## Phase 3 — Claude Code plugin

Package the in-agent experience. Plugin name `goals` ⇒ commands auto-namespace as
`/goals:<cmd>`.

**Tasks**
- `.claude-plugin/plugin.json` — plugin manifest (name `goals`, version,
  description, command/skill/hook locations).
- `commands/` — prompt files driving the loop, each calling the CLI:
  - `create.md` → `/goals:create "<objective>"` (start in-place + walk phase 1).
  - `next.md` → `/goals:next` (refresh + drive the current phase).
  - `check.md` → `/goals:check` (status/brief).
  - `status.md`, `phase.md` (evidence/review/accept helpers), `improve.md`
    (memory/loop-improve), `dashboard.md`.
  - Bodies are explicit loop instructions ("read goal.json, work the current
    phase, record evidence via `goals phase evidence`, review, accept") so
    automation doesn't depend on the model guessing.
- `skills/` — reuse the bundled `goals-*` skills; add a `goals-driver` skill
  describing the phase loop for model-initiated use outside the slash commands.
- `hooks/hooks.json`:
  - **SessionStart** → script runs `goals context --json` (if a goal exists) and
    returns it as `additionalContext`, so every session auto-knows the active
    goal. (Silent; no prompt.)
  - **Stop (opt-in)** → blocks stop until the current phase is accepted; gated
    behind a setting (e.g. `GOALS_ENFORCE=1` or plugin config) so it never nags
    by default.
- Marketplace: `.claude-plugin/marketplace.json` in this repo so users can
  `/plugin marketplace add ShivamGupta42/goals` then `/plugin install goals`.

**Verify**
- Local install: `/goals:create "demo"` starts an in-place goal and the agent
  works phase 1. (verify: manual session smoke + a test that lints command/hook
  files exist and are valid JSON/markdown)
- SessionStart injects the active goal block when one exists, nothing when none.
  (verify: run the hook script directly, assert output)
- Stop hook does nothing unless enabled. (verify: hook script test, both modes)
- ruff + pytest green; plugin manifest validates.

**Risk:** plugin/hook APIs evolve. Mitigation: hook scripts are thin shims over
the CLI; the contract is "run a command, emit text."

---

## Phase 4 — Codex setup + one-step install

**Tasks**
- `goals setup --agent claude|codex|both [--dry-run]`:
  - **claude**: ensure the plugin is discoverable (register the marketplace /
    copy `commands` + `skills` + `hooks` into `~/.claude/` as a fallback for
    non-marketplace installs); install bundled skills.
  - **codex**: install skills into `~/.codex/skills` (reuse
    `skill_discovery.install_bundled_skills`), write Codex prompt files for the
    `goals` verbs, and sync the `AGENTS.md` managed block
    (`portability.sync_context_files`).
  - Idempotent; `--dry-run` prints what it would do; collision-safe (reuse the
    existing skill-install safety: never clobber a differing user file without
    `--force`).
- Print a short "you're set up" summary with the first command to run.

**Verify**
- `goals setup --agent both` wires both agents; re-running is a no-op. (verify:
  tests place files in temp HOME dirs, assert idempotency + dry-run)
- Codex path writes `~/.codex/skills` + AGENTS.md block without clobbering user
  content. (verify: tests)
- ruff + pytest green.

---

## Phase 5 — Migration, docs, deprecation framing

**Tasks**
- README: lead with the in-agent flow (`/plugin install goals` → `/goals:create`)
  ; demote the CLI to "local AI / scripting / fallback." Document `--worktree`
  as opt-in isolation.
- Document the `/goal` (Claude built-in) vs `/goals:create` (this plugin)
  distinction explicitly.
- Update `docs/SELF_EVOLUTION.md` and the quickstart for the in-place + plugin
  model.
- Note MCP as a deferred, optional future surface (the seam, not a promise).

**Verify**
- A brand-new-user quickstart that goes install → first goal → progress, with no
  `cd` and no paste. (verify: doc walkthrough matches real command output)
- Final branch-scoped review; ruff + pytest green.

---

## Out of scope (flag, don't smuggle in)

- **MCP server** — deferred; documented as an optional later surface.
- Removing the CLI or the worktree path — both stay (fallback + opt-in).
- Mode B autonomous execution; non-Claude/Codex adapters.
- Rewriting the core engine — phases/evidence/gates/portability are reused as-is.

## Cross-cutting back-compat & safety

- Existing worktree goals must load and run unchanged.
- In-place must never write outside the current repo's `.agent-workflow/`.
- Skill/setup installers never clobber a user's differing file without `--force`
  (reuse the shipped collision-safe install).
- Stop hook is opt-in; SessionStart is silent.

## Open questions to confirm before/while building

1. **In-place on the default branch:** allow with a note (proposed), or
   auto-create a feature branch, or refuse? → *proposed: allow + note.*
2. **Plugin distribution:** this repo self-hosts `.claude-plugin/marketplace.json`
   (proposed), or a separate marketplace repo?
3. **`goals setup` scope:** perform the file/config writes idempotently with
   `--dry-run` (proposed), or only print the steps for the user to run?
4. **Codex skill-execution parity:** verify during Phase 4; CLI + AGENTS.md is
   the fallback if Codex skill support is weaker than Claude's.

## Suggested sequencing

Phases are ordered so `main` stays shippable each step: 1 (in-place) and 2
(CLI ergonomics) are pure additions usable immediately; 3 (plugin) and 4 (setup)
layer the native surfaces; 5 is docs. Each phase ends green (ruff + pytest) with
tests for new paths.
