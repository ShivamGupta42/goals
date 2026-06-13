# Goals

**Goals helps AI agents finish bigger tasks without losing track.**

Goals breaks a goal into steps, gives each step a durable state file, checks the
work, remembers what happened, and shows progress in a simple dashboard.

Claude Code and Codex already have native `/goal` loops. Goals does not replace
those loops. It gives them a file-backed workflow layer: worktrees, phases,
evidence, review gates, decisions, learnings, and a status page.

## Status

This repository is an early MVP. Mode A is implemented first:

- Claude or Codex owns the outer native `/goal` loop.
- Goals owns project-local state and instructions.
- The CLI does not launch or control Claude/Codex processes.

Mode B, a standalone runner for local AI or schedulers, is represented by the
runtime interfaces but intentionally not complete in this version.

See [ROADMAP.md](ROADMAP.md) for planned directions that are intentionally not
implemented yet.

## Quick Start

```bash
uv sync
uv run goals create "Add tags to tasks and update tests" \
  --why "Make tasks easier to organize." \
  --adapter claude
uv run goals status
uv run goals run --adapter codex
uv run goals dashboard
uv run goals architecture show
uv run goals ecosystem recommend
uv run goals eval scenarios --adapter claude
uv run goals adapter check codex
```

Goals writes generated state under `.agent-workflow/goals/` in the goal worktree.
That directory is ignored by default because it can include local paths and
private run history.

## Mode A

Mode A is the native-agent path. Goals does not launch Claude or Codex for you;
it generates a concrete `/goal` handoff for the adapter you choose.

```bash
uv run goals run --adapter claude
uv run goals run --adapter codex
```

The generated handoff includes the active phase, the goal state file, the
dashboard path, phase acceptance criteria, recommended checks, and an evidence
JSON template. Agents can write that template to a file and record it without
shell-escaping a large JSON string:

```bash
uv run goals phase evidence P1 --file .agent-workflow/goals/<goal-id>/evidence-p1.json
uv run goals phase review P1
uv run goals phase accept P1
```

Agents can explain only important decisions with active goal history:

```bash
uv run goals decision explain --file decision.json --level basic
```

Agents can also ask Goals which skills or plugins fit the current phase:

```bash
uv run goals ecosystem recommend
```

Mode A handoffs include these recommendations automatically. Goals does not run
external tools for the agent; it explains what looks relevant and whether user
approval is needed.

Agents and technical reviewers can inspect a goal-level architecture map:

```bash
uv run goals architecture show
uv run goals architecture update --file architecture.json
```

The dashboard is the simple status view for end users. `architecture.md` is the
deeper Markdown/Mermaid view for people who want to question what is built,
planned, blocked, or deferred.

## Public Safety

During local work, generated goal state is expected:

```bash
uv run goals safety-check --mode local
```

Before publishing a repository that has used Goals, use publish mode:

```bash
uv run goals safety-check --mode publish
```

The scanner checks for secrets, local paths, prompt-injection text, destructive
operations, generated private state, license hygiene concerns, and external
supply-chain references.

## Self-Evolution

Goals includes scenario evaluations for personal, technical, business,
self-evolution, and ecosystem use cases. These evaluations focus on the end-user
experience of decisions and visualization, not just backend state:

```bash
uv run goals eval scenarios --adapter claude
```

See [docs/SELF_EVOLUTION.md](docs/SELF_EVOLUTION.md) for the current loop.
