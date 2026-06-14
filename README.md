# Goals

Goals helps Codex, Claude Code, and other local agents finish bigger repo tasks
without losing the thread.

It does not replace the native agent. It is the **durable, vendor-neutral layer
around the work**: a goal worktree, phase state, evidence, acceptance checks,
decisions, and a dashboard a human can read — plus a portable goal spec any agent
can pick up.

## Why Goals stays useful even as Claude Code and Codex evolve

Native agents keep getting better at the *inner loop* (write code, run tests).
But the loop primitives they ship are, by design, vendor-locked and short-lived:

- Claude Code's `/goal` is **session-scoped** — it disappears on `/clear`, and
  its checker only reads the transcript, never the proof.
- `TodoWrite` lives and dies inside one session.
- `AGENTS.md` (the cross-vendor standard) is **static instructions only** — no
  task state, no "done" semantics, no evidence.
- Cursor/Windsurf memories are proprietary and IDE-bound.

No vendor will build a portable, durable, *out-of-their-tool* goal+acceptance+
evidence ledger, because that works against their lock-in. That gap is what Goals
fills, and it is the part that survives any single tool evolving:

1. **Ownership & durability** — goal, acceptance criteria, and evidence are plain
   files in your repo that survive `/clear`, crashes, and switching agents.
2. **Evidence-based "done"** — captured checks and acceptance state, not
   transcript-skimming.
3. **Vendor-neutral handoff** — one goal state read by Claude *and* Codex *and*
   the next tool you try.
4. **Auditable history** — an append-only event log independent of any
   proprietary store.

## Run it inside Claude Code or Codex (recommended)

The smoothest way to use Goals is **from inside your agent** — no copy-paste, no
`cd`. One command wires it up:

```bash
goals setup --agent both      # or: --agent claude | --agent codex  (use --dry-run to preview)
```

- **Claude Code** — registers this repo as a plugin marketplace and enables the
  `goals` plugin, so you get namespaced slash commands and a SessionStart hook
  that auto-loads the active goal:

  | Command | What it does |
  | --- | --- |
  | `/goals:create "<objective>"` | Start a goal and begin its first phase. |
  | `/goals:next` | Work the current phase, record evidence, review, accept. |
  | `/goals:check` | Status, proof, and what (if anything) needs you. |
  | `/goals:diagram` | Render the goal's architecture/loop as a diagram. |
  | `/goals:improve` | Turn evidence-backed memory into a reviewable change set. |

  > **`/goals:create` is *not* Claude Code's built-in `/goal`.** `/goal` is
  > Claude's session-scoped stop-condition; `/goals:*` are this plugin's
  > namespaced commands. They never collide.

  An **opt-in** Stop hook (set `GOALS_ENFORCE=1`) keeps the session working until
  the current phase is accepted. Off by default — it never nags.

- **Codex** — installs Goals' skills into `~/.codex/skills`; run
  `goals context sync` in a project so the active goal shows up in `AGENTS.md`.
  Codex then drives the same `goals` CLI.

The CLI below is always available too — it's the fallback for local AI and
scripting.

### Where the work happens

- **On `main`/`master`** Goals never touches your base checkout — it creates an
  isolated worktree (its own `goal/<id>` branch).
- **On a feature branch** it asks (interactively) or takes `--worktree` /
  `--in-place`. Worktrees are how you run **several goals at once**.
- **In a non-git directory** it works in place and tells you there's no isolation.

## The simple command set

Most users only need these four:

| Command | What it does |
| --- | --- |
| `goals start` | Creates the goal workspace (worktree on main, or in place — see above), goal state, dashboard, and first agent handoff. |
| `goals next` | Refreshes generated files and prints the paste-ready `/goal` handoff for Codex or Claude. |
| `goals check` | Combines brief, checkpoint, issues, merge readiness, and architecture into one status view (`--json` for agents). |
| `goals view` | Refreshes the dashboard, architecture map, and portable `.goals/` spec, then prints their paths. |
| `goals diagram` | Renders the goal's architecture or loop as Mermaid or a standalone `.excalidraw` file. |

## Portability: the part native tools won't build

Three commands turn the internal goal into artifacts any agent can use:

| Command | What it does |
| --- | --- |
| `goals export` | Writes `.goals/GOAL.md` + `.goals/goal-state.json` — a sanitized, **committable** portable spec (the "AGENTS.md for task state"). |
| `goals context sync` | Syncs a managed goal block into `AGENTS.md` and `CLAUDE.md`, preserving your hand-written content, so a team using both Claude and Codex never drifts. |
| `goals emit --agent claude\|codex` | Emits a transcript-verifiable native stop-condition from the current phase's acceptance criteria — paste it straight into Claude Code's `/goal` or Codex. |

`goals view` runs `export` for you, so the portable spec stays fresh as part of
the normal loop. Unlike `.agent-workflow/` (local run state, git-ignored, may
contain machine paths), everything under `.goals/` is path-free and safe to
commit.

## Visual loop builder

Compose, lint, and improve a goal loop without hand-writing the spec. The
builder is a text-based terminal UI; the static HTML is an **export** of the same
design, never a parallel artifact.

| Command | What it does |
| --- | --- |
| `goals loop build` | Interactive builder: add/edit/reorder/delete phases, set acceptance and termination conditions, and attach skills discovered live from `~/.claude/skills` and `~/.codex/skills`. On `save` it writes the design, the portable spec (`goal-state.json` + `GOAL.md`), and a standalone `loop.html`. Use `--script FILE` to replay commands. |
| `goals loop export` | Re-render a saved design to HTML (and the portable spec). |
| `goals loop check [--fix]` | Lint the loop for issues — no termination condition, vague/untestable acceptance, duplicate or empty phases, unknown skill references, missing evidence requirements. `--fix` applies only the safe, reversible fixes and is idempotent. |
| `goals loop detect <phase>` | After a phase is accepted, log any regressions (with evidence) into self-evolution memory, routing each as needs-attention-now or deferred. |
| `goals loop improve [--apply]` | Turn accumulated, evidence-backed memory into a reviewable change set targeting task execution or the loop design; `--apply` applies only the safe loop-design fixes. |

One source of truth: `LoopDesign` compiles to the existing portable spec (reusing
the same `portability.py` `goals export` uses) and renders the HTML, so the two
surfaces never drift. Skills are stored as name references; which agent has each
one — and the suggestion to install a Claude-only skill into `~/.codex/skills` so
the loop runs under both — is resolved live at render time.

```bash
goals loop build --script examples/visual-builder.loop --out .goals
goals loop check --out .goals
open .goals/loop.html
```

The builder dogfoods the repo: `examples/visual-builder.loop` reproduces this
feature's own three-phase goal spec, and it lints clean.

**Out of scope** (deliberately not built here): a web server or live multi-user
editing; autonomous execution of the designed loop; non-Claude/Codex adapters.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) — used for every
  install and command below. `uv` also auto-provisions Python 3.11+, so you do not need
  to install Python separately. On macOS/Linux:
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- `git` — `goals start` operates on a clean git repository with at least one commit.

## Install

From this repository (puts `goals` on your PATH):

```bash
uv tool install --editable .
```

For development inside this repository:

```bash
uv sync
uv run pytest -q
```

## Use with Codex or Claude Code

Run inside a clean git repo with at least one commit:

```bash
goals start "Ship the onboarding cleanup" --agent codex   # or --agent claude
cd <worktree printed by goals>
goals next --agent codex                                   # paste the output into the agent
```

Copy the handoff to your clipboard with your platform's clipboard tool
(`pbcopy` on macOS, `xclip`/`wl-copy` on Linux, `clip` on Windows), e.g.
`goals next --agent codex | pbcopy`.

If the native `/goal` feature is not enabled locally, the generated prompt still
works: paste it into the current session and let Goals remain the state layer.

During the run:

```bash
goals check                  # one-screen health view
goals view                   # refresh dashboard + portable spec
goals next --agent codex     # next paste-ready handoff
```

## How it works

`goals start` creates a git worktree and writes generated state under:

```text
.agent-workflow/goals/<goal-id>/   # local run state, git-ignored
.goals/                            # portable, committable goal spec
```

The native agent owns the work. Goals owns the structure around the work:

- phases and acceptance criteria
- proof and evidence
- user-facing decisions
- merge-readiness and architecture checks
- a dashboard for humans
- the portable goal spec other agents can read

## Extending Goals

Goals is a small workflow layer over composable primitives.

- Add or change high-level workflows in `src/goals/workflows.py`.
- Keep `src/goals/cli.py` thin: commands mostly call workflow helpers or domain
  modules.
- Add reusable capabilities as focused modules under `src/goals/`.
- Ship goals' own skills as `SKILL.md` dirs under `skills/`; add permission and
  adapter metadata under `registries/*.yml`.

Skills are **discovered live**, never registered: `goals skills list` reads
`~/.claude/skills`, `~/.codex/skills`, and goals' own bundled `skills/`. There is
no skill catalog to maintain. `goals skills install --target claude|codex|both`
is optional — only needed to invoke a bundled skill from a raw agent session.

Advanced building blocks still available for agents and scripts:

```bash
goals phase evidence | review | accept
goals brief
goals issues
goals merge-check
goals checkpoint current
goals decision brief
goals source add | freshness | list
goals architecture check
goals skills list | install
goals permission check
goals validate | doctor | repair
```

## Status

Early MVP. Mode A is implemented:

- Codex or Claude owns the native goal loop.
- Goals owns project-local state, evidence, checks, dashboard, and the portable
  spec.
- The CLI does not launch or control agent processes.

See [ROADMAP.md](ROADMAP.md) for planned directions.
