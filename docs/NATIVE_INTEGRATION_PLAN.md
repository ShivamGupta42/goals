# Native Integration Plan — goals inside Claude Code & Codex

Make `goals` work **from inside** Claude Code and Codex: no copy-paste handoff,
one-step install, the agent works seamlessly. The CLI stays as the execution
engine and the local-AI / scripting fallback. **No MCP** — skills + slash
commands + hooks over the CLI (MCP is a deferred, optional surface). Plus
deterministic architecture-diagram generation.

## Locked decisions

1. **Name:** keep `goals`. Disambiguate from Claude Code's built-in `/goal` via
   plugin command namespacing — `/goals:create`, `/goals:check`, … (a plugin
   named `goals` namespaces its commands as `/goals:<cmd>` automatically).
2. **Workspace:** **create a git worktree and work there** when in a git repo
   (isolation preserved; the agent works in the worktree so the human never has
   to `cd`/paste). **If the current directory is not a git repo,** work in place
   there and **inform the user**.
3. **Integration:** **skills + slash commands + hooks over the CLI.** MCP
   deferred — everything routes through the CLI, so MCP can be added later as a
   thin extra surface (Claude plugins can ship a `.mcp.json`) without touching
   the core.
4. **Install:** **one command that actually executes** — `goals setup --agent
   claude|codex|both` performs the install (idempotent; `--dry-run` available),
   so a single command brings everything into action. Plus a self-hosted Claude
   Code plugin marketplace in this repo.
5. **Diagrams:** generate clean architecture diagrams (`.excalidraw` + Mermaid,
   optional PNG/SVG) deterministically from goals' own architecture map / loop
   design, reusing the format rules proven by the `excalidraw` skill.

## Why this shape (stability rationale)

Both skills and MCP are only *invocation surfaces* over the existing `goals`
CLI. Skills add a text file pointing the model at the CLI; MCP adds a
long-running process + protocol + a second execution path to keep in sync. The
CLI is the stability anchor; skills/commands/hooks are thin, swappable layers.
Loop *automation* comes from command-prompt bodies + hooks, not from hoping the
model invokes a skill.

## Current state (what we change / reuse)

- `goals start` always creates a sibling worktree and prints a paste-the-handoff
  next step (`runtime.create_goal` → `require_clean_repo` + `create_worktree`,
  runtime.py:91/98). We keep the worktree as the default but drive it from inside
  the agent, and add a non-git in-place fallback.
- Reuse: bundled skills, live discovery, `goals skills install`, portable spec
  (`.goals/`), context sync into `AGENTS.md`/`CLAUDE.md`
  (`portability.sync_context_files`), the Mode A handoff, and the structured
  `GoalArchitectureMap` + `LoopDesign` models (for diagrams).
- No plugin/command/hook scaffolding exists yet (greenfield).
- Some read commands already support `--json`.

## Plugin distribution facts (confirmed)

Standard single-tool pattern: **the repo IS its own marketplace AND the plugin**
(as e.g. `context-mode` does).

- **Plugin manifest:** `.claude-plugin/plugin.json` — `name`, `description`,
  `version`, `author`.
- **Marketplace manifest:** `.claude-plugin/marketplace.json` at repo root —
  `name`, `version`, `owner`, `plugins: [{ name, description, source: "./",
  category }]` (with `$schema`).
- **Plugin contents:** `commands/*.md`, `skills/`, `hooks/hooks.json`, optional
  `agents/`, optional `.mcp.json`.
- **Install UX:** `/plugin marketplace add ShivamGupta42/goals` then `/plugin
  install goals@goals` (or settings `extraKnownMarketplaces` + `enabledPlugins`).
- **Commands namespace** as `/goals:<command>`.
- **Hook scripts** reference plugin-relative paths via `${CLAUDE_PLUGIN_ROOT}`.

---

## Phase 1 — Worktree-by-default workspace + non-git in-place fallback

**Tasks**
- Keep worktree creation as the default for git repos, but make it drivable from
  inside the agent (the agent works in the worktree; the human never `cd`s).
- Add a **non-git in-place** path: if `cwd` is not a git repo, do **not** error —
  track and work in place under `<cwd>/.agent-workflow/goals/<id>` and **print a
  clear notice** ("not a git repo — working here directly; no isolation").
  (`create_goal`/`_ensure_repo` currently require `git_root`; add this branch.)
- `goals start` flags: keep worktree default; add `--in-place` to force in-place
  inside a git repo; keep `--new` for greenfield.
- On default branch with worktree default: unaffected (worktree gets its own
  `goal/<id>` branch, as today).
- Make the start output agent-friendly: it states the worktree path and that the
  agent will work there (the plugin command + SessionStart hook handle the rest);
  no "paste this" framing.
- Back-compat: existing worktree goals load and run unchanged.

**Verify**
- `goals start "x"` in a git repo → creates the worktree + `goal/x` branch
  (test).
- `goals start "x"` in a **non-git** dir → works in place, prints the notice,
  state under `cwd/.agent-workflow/goals/` (test).
- `goals start --in-place "x"` in a git repo → no worktree, tracks current branch
  (test).
- Existing worktree-goal fixtures still load; ruff + pytest green.

---

## Phase 2 — CLI ergonomics for in-agent use

**Tasks**
- Add `--json` to every read command missing it (`status`, `check`, `next`,
  `brief`, `issues`, `checkpoint current`, phase reads).
- Add `goals context [--json]` — emit the compact active-goal block for the
  SessionStart hook to inject (objective, current phase, acceptance, waiting-on,
  worktree path, next safe step). Reuse `portability.render_context_block`.
- Keep the improved `GoalsError` messages (already on `main`).

**Verify**
- Every read command emits valid JSON under `--json` (tests parse it).
- `goals context --json` returns the active-goal block; clean error when none.
- ruff + pytest green.

---

## Phase 3 — Architecture diagram generation

Generate clean diagrams from goals' **structured** data — deterministic and
testable, unlike freehand code analysis. Reuse the `excalidraw` skill's format
rules (credit in code).

**Tasks**
- `goals diagram [--source architecture|loop] [--format excalidraw|mermaid]
  [--out PATH]`:
  - **Mermaid** (default, zero-dep): render `GoalArchitectureMap` (or
    `LoopDesign` phases) as a flowchart — nodes colored/classed by status
    (built/planned/blocked/deferred), edges from the map's relations. Renders in
    GitHub/markdown and the dashboard.
  - **Excalidraw**: emit valid `.excalidraw` JSON with a deterministic layered
    layout, applying the proven rules:
    - rectangles only (no diamonds);
    - every labeled shape = a shape with `boundElements` **plus** a separate
      `text` element with `containerId`;
    - elbow arrows (`roughness:0`, `roundness:null`, `elbowed:true`);
    - arrows attach at edge-math coordinates (top/bottom/left/right), not
      centers;
    - color by node status.
- Bundle a `references/` doc with the excalidraw JSON-format + arrow rules
  (progressive disclosure), adapted from the reference skill.
- Optional PNG/SVG export behind an extra (`--png`/`--svg`, Playwright as an
  optional dependency — never required for the core).
- Embed the Mermaid diagram into the dashboard and `GOAL.md`.
- Ship as a skill (`goals-architecture-diagram` SKILL.md) so the agent can
  "diagram this goal," routing to `goals diagram`.

**Verify**
- `goals diagram --format mermaid` emits valid Mermaid; node classes map to
  status (test).
- `goals diagram --format excalidraw` emits valid JSON that opens in Excalidraw;
  **every labeled shape has its bound text element + `containerId`**, arrows
  attach at edges, no diamonds (structural tests assert this).
- Empty/edge-case maps render without crashing.
- ruff + pytest green.

---

## Phase 4 — Claude Code plugin

Package the in-agent experience. Plugin name `goals` ⇒ `/goals:<cmd>`.

**Tasks**
- `.claude-plugin/plugin.json` (name `goals`, version, description, author).
- `.claude-plugin/marketplace.json` at repo root (self-hosted marketplace
  listing the `goals` plugin with `source: "./"`).
- `commands/*.md` — explicit loop-driving prompts that call the CLI and operate
  in the worktree:
  - `create.md` → `/goals:create "<objective>"` (start → work phase 1 **in the
    worktree**).
  - `next.md`, `check.md`, `status.md`, `phase.md`, `improve.md`, `diagram.md`,
    `dashboard.md`.
  - Bodies are explicit ("read goal.json, work the current phase **in the
    worktree path**, record evidence via `goals phase evidence`, review, accept")
    so automation doesn't depend on the model guessing, and the human never
    `cd`s.
- `skills/` — reuse bundled `goals-*` skills + the new diagram skill + a
  `goals-driver` skill describing the phase loop.
- `hooks/hooks.json`:
  - **SessionStart** → `${CLAUDE_PLUGIN_ROOT}` script runs `goals context --json`
    and returns `additionalContext` (and, if the active goal is in a worktree,
    states the worktree path). Silent; no prompt.
  - **Stop (opt-in)** → block stop until the current phase is accepted; gated by
    a setting so it never nags by default.

**Verify**
- Local install via the marketplace; `/goals:create "demo"` starts a goal and the
  agent works phase 1 in the worktree (manual session smoke + tests that the
  manifests/command/hook files are valid).
- SessionStart injects the active-goal block when one exists, nothing when none
  (run the hook script directly; assert output).
- Stop hook is inert unless enabled (test both modes).
- ruff + pytest green; manifests validate.

---

## Phase 5 — One-command setup + Codex (verified)

**Tasks**
- `goals setup --agent claude|codex|both` — **executes** the install
  (idempotent, collision-safe; `--dry-run` to preview):
  - **claude**: register the self-hosted marketplace + enable the plugin (write
    `extraKnownMarketplaces` + `enabledPlugins`), and install bundled skills.
  - **codex**: install skills into `~/.codex/skills`
    (`skill_discovery.install_bundled_skills`), write Codex prompt files for the
    `goals` verbs, and sync the `AGENTS.md` managed block
    (`portability.sync_context_files`).
  - Print a one-line "you're set up — run /goals:create" summary.
- **Verify Codex actually works** (not assumed):
  - drive a real check with `codex exec` (the CLI is available in this env) — run
    `goals start`, `goals next`, `goals phase evidence/review/accept`, `goals
    diagram` inside a Codex run and confirm the loop completes;
  - confirm Codex reads the synced `AGENTS.md` block and the installed skills;
  - confirm the CLI + `AGENTS.md` fallback works even if Codex skill execution is
    weaker than Claude's.

**Verify**
- `goals setup --agent both` wires both agents; re-running is a no-op; `--dry-run`
  previews (tests in temp HOME dirs assert placement + idempotency).
- Codex smoke via `codex exec` completes a goal loop (recorded transcript).
- ruff + pytest green.

---

## Phase 6 — Migration, docs, deprecation framing

**Tasks**
- README: lead with the in-agent flow (`/plugin marketplace add …` → `/plugin
  install goals@goals` → `/goals:create`, or `goals setup --agent both`). Demote
  the CLI to "local AI / scripting / fallback." Document `--in-place` and the
  non-git behavior.
- Document `/goal` (Claude built-in) vs `/goals:create` (this plugin).
- Update `docs/SELF_EVOLUTION.md` + a fresh-user quickstart (install → first goal
  → progress, no paste).
- Note MCP as a deferred optional surface (the seam, not a promise).

**Verify**
- Quickstart matches real command output; final branch-scoped review; green.

---

## Out of scope (flag, don't smuggle in)

- **MCP server** — deferred (documented as an optional later surface; plugins can
  ship `.mcp.json` when we want it).
- Removing the CLI — it stays (engine + fallback).
- Mode B autonomous execution; non-Claude/Codex adapters.
- Engine rewrite — phases/evidence/gates/portability/architecture reused as-is.
- Playwright/PNG export is optional, never a required dependency.

## Cross-cutting back-compat & safety

- Existing worktree goals must load and run unchanged.
- In-place (non-git) must never write outside `<cwd>/.agent-workflow/`.
- Setup/skill installers never clobber a user's differing file without `--force`
  (reuse the shipped collision-safe install).
- Stop hook opt-in; SessionStart silent.

## Resolved earlier open questions

1. Workspace on default branch → **worktree by default** (own `goal/<id>`
   branch); non-git dir → in-place + notice. *(resolved)*
2. Plugin distribution → **self-hosted single repo** = marketplace + plugin.
   *(resolved, mechanics confirmed)*
3. `goals setup` → **executes**, one command, idempotent, `--dry-run` optional.
   *(resolved)*
4. Codex parity → **verified in Phase 5** via `codex exec`; CLI+AGENTS.md is the
   fallback. *(resolved)*

## Sequencing

1–2 (workspace + CLI ergonomics) and 3 (diagrams) are additive and usable
immediately; 4 (plugin) wires the commands/skills/diagram; 5 (setup + Codex)
makes it one-command and verifies Codex; 6 is docs. Each phase ends green (ruff +
pytest) with tests for new paths.
