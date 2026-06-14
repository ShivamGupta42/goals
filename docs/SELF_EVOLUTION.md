# How Goals Stays Indispensable

Native agents own the inner loop. Claude Code, Codex, Cursor, and Windsurf all
ship fast, capable goal/task primitives — but those primitives are
vendor-locked and short-lived:

- Claude `/goal` is session-scoped and dies on `/clear`. Its checker reads only
  the transcript, so "done" is asserted, not proven.
- TodoWrite is per-session scratch state.
- AGENTS.md is static instructions with no task state.
- Cursor/Windsurf memories are proprietary and non-portable.

No vendor will build a portable, durable, out-of-tool goal + acceptance +
evidence ledger — it fights their lock-in. **Goals fills exactly that gap.** Its
durable value is:

- **Ownership and durability of state** — the goal lives in your repo, not a
  vendor's session.
- **Evidence-based "done"** — acceptance is backed by recorded proof, not a
  transcript claim.
- **Vendor-neutral handoff** — the same goal moves between Claude, Codex, and any
  other tool.
- **An auditable append-only event log** — every change is recorded and
  inspectable.

This document describes how Goals delivers that durable value and how it fits
alongside native loops without trying to replace them.

## Portability Layer

The portability layer is the clearest expression of the durable-value thesis. It
turns live goal state into something that outlives any single session or tool.

```bash
uv run goals export
uv run goals context sync --target both
uv run goals emit --agent claude
uv run goals emit --agent codex
```

`export` writes `.goals/GOAL.md` plus `.goals/goal-state.json` — a sanitized,
committable, vendor-neutral portable goal spec (the "AGENTS.md for task state").
It is versioned by `PORTABLE_SPEC_VERSION` (currently 1) and safe to commit so
the goal travels with the repo. `goals view` runs `export` automatically, so the
portable spec stays current as you work. Implementation lives in
`src/goals/portability.py`.

`context sync` writes a managed
`<!-- goals:context:start -->`…`<!-- goals:context:end -->` block into AGENTS.md
and CLAUDE.md, preserving everything a human wrote outside the block. Use
`--target agents`, `--target claude`, or `--target both` to choose where the
block goes. This keeps a native agent's static instructions pointed at the
current goal without overwriting human-authored content.

`emit` produces a transcript-verifiable native stop-condition derived from the
current phase's acceptance criteria, ready to paste into Claude `/goal` or Codex.
The native loop runs fast and owns execution; the emitted condition makes its
stop point answerable from recorded acceptance criteria instead of a vague
transcript judgment.

## Memory Loop

Goals can record repeated friction and derive improvement suggestions, then sync
sanitized lessons across similar projects:

```bash
uv run goals memory record "Repeated setup confusion" --area skill --kind friction
uv run goals memory absorb
uv run goals memory suggest
uv run goals memory sync ../similar-goals-project
```

Use `record` when an agent notices a reusable issue during work. Use `absorb`
after a goal has evidence, blockers, failed reviews, or learnings that should
become reusable memory. `suggest` surfaces an improvement only when a pattern
repeats or a gap is high severity.

Use `memory sync` when another Goals project has already exposed a useful lesson.
It is a dry run by default and imports only sanitized suggestions; raw source
summaries and evidence refs stay out unless explicitly requested.

Memory is local generated state under `.agent-workflow/self-evolution/`. It is
not meant for public commits.

## Decision Rule

Goals should not ask the user about every choice. Only **blocking** decisions are
user-facing by default.

The agent can decide reversible or low-risk details itself when it records:

- the assumption it made,
- why it is reversible,
- what evidence proves the result,
- how to undo or change direction later.

The user should see a simple question only when the answer changes safety,
privacy, cost, external side effects, data migration, or the core direction of
the goal.

Agents can generate a user-ready explanation from the active goal history:

```bash
uv run goals decision brief
uv run goals decision explain --file decision.json --level basic
uv run goals decision explain --file decision.json --level detailed
uv run goals decision explain --file decision.json --level technical
```

`decision brief` is the non-technical first pass: it shows only choices that need
the user, the recommended reply, what happens after, and how many routine choices
can stay with the agent. The explainer is clear about which facts came from
project history and which are current agent judgment, so the user can tell
whether they really need to be interrupted.

Checkpoints apply the same idea to phase progress. `goals checkpoint current`
shows the current validation point in plain language: what is being checked, who
is waiting, what proof exists, what remains unresolved, and the next safe step.
Required checkpoints must pass or be waived before a phase can be reviewed or
accepted, so the agent keeps working on repairable gaps and stops only for
approvals or understanding that genuinely needs the user.

## Ecosystem Fit

Claude Code and Codex already provide native loops, skills, plugins, tools, and
permissions. **Goals does not replace them.** Its job is the durable layer
underneath the native inner loop. Goals provides:

- durable goal state across turns, sessions, and `/clear`,
- phase evidence and review gates so "done" is proven,
- a portable, committable goal spec (`goals export`) that any tool can read,
- adapter-aware native stop-conditions (`goals emit`) and synced context blocks
  (`goals context sync`),
- registries for skills, plugins, and adapters with `goals ecosystem recommend`
  and a coordinator merge view with `goals ecosystem merge`,
- a permission policy (`goals permission check`) that keeps routine tool choices
  with the agent while surfacing external, costly, or destructive actions,
- source evidence (`goals source add|freshness|list`) so research and business
  claims are inspectable and stale evidence becomes agent repair work unless a
  high-stakes claim needs the user,
- code-derived architecture checks (`goals architecture check`) that compare
  changed files and evidence refs with the goal architecture map,
- a read-only dashboard that makes progress and blockers visible,
- decision explanations non-technical users can understand.

Before escalating to the user, agents should run the issue report:

```bash
uv run goals brief
uv run goals issues
uv run goals merge-check
```

`brief` is the non-technical first pass: what is happening, what needs the user,
what the agent can do next, and what proof exists. `issues` separates important
user questions from agent-side repair actions. `merge-check` is the coordinator
pass before merging: it explains whether migration ordering, branch drift, dirty
sibling worktrees, overlapping files, or high-risk approval is still unresolved,
and keeps routine repair work with the agent.

Goals must always know what phase it is in, what evidence exists, what remains
uncertain, whether a decision really needs the user, and whether an external tool
needs approval before use. Native loops handle the fast execution; Goals keeps
the durable, portable, evidence-backed record of what was actually achieved.
