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

## Quick Start

```bash
uv sync
uv run goals create "Add tags to tasks and update tests"
uv run goals status
uv run goals dashboard
uv run goals adapter check codex
```

Goals writes generated state under `.agent-workflow/goals/` in the goal worktree.
That directory is ignored by default because it can include local paths and
private run history.

## Public Safety

Before publishing a repository that has used Goals, run:

```bash
uv run goals safety-check
```

The scanner checks for secrets, local paths, prompt-injection text, destructive
operations, generated private state, license hygiene concerns, and external
supply-chain references.

