# Roadmap

This file tracks larger product directions that are intentionally not being built
yet. Each entry explains the user value, the likely shape, and the questions to
resolve before implementation. It is honest about what already exists in the
simplified tool versus what is still ahead.

The spine of the roadmap is the **portability layer**: native agents own the
inner loop, but their goal/task primitives are vendor-locked and short-lived.
Goals owns the durable, portable, evidence-backed goal state in your repo. The
directions below deepen that durable value rather than chase parity with native
loops.

For the Trust V1 dogfood follow-up plan, including the 48-issue improvement
inventory and the proposed capability-gap architecture, see
[`docs/TRUST_V1_LONG_TERM_IMPROVEMENT_PLAN.md`](docs/TRUST_V1_LONG_TERM_IMPROVEMENT_PLAN.md).

## Capability gap management

**Status:** Implemented (read-only vertical slice). `goals capability check`
exists with text/JSON output, `--strict`, `--agent auto|claude|codex`, and
explicit `--need ...` inputs for model-authored requirements. The analyzer also
infers obvious browser/UI needs from goal and phase text, compares them against
live skill discovery, and reports missing, bundled-but-not-installed, and
wrong-agent skills.

Capability gaps now surface in `goals issues`, `goals brief`, `goals check`, the
dashboard, and full `goals next --full` handoffs. Codex skill discovery uses
`~/.agents/skills` as the primary native root and keeps legacy `~/.codex/skills`
as a fallback.

### Direction

- Durable capability profile and source events.
- User-approved external skill/plugin source governance.
- Browser/tool preflight adapters and dashboard verification wrappers.
- Artifact classes and repair plans tied to capability gaps.
- Repeated capability-gap memory promotion.

### Open Questions

- Should required missing capability be a P0 issue, or stay P1 while `goals check`
  fails through its combined health gate?
- Which external skill/plugin source descriptors should ship first, if any?
- How should plugin/cache tool inventory be exposed without coupling Goals to one
  host agent's private runtime layout?

## Portable goal-state spec v2

**Status:** Forward-looking. v1 exists today. `goals export` writes
`.goals/GOAL.md` plus `.goals/goal-state.json` — a sanitized, committable,
vendor-neutral portable goal spec (the "AGENTS.md for task state"), versioned by
`PORTABLE_SPEC_VERSION` (currently 1). `goals view` runs it automatically.

The v1 spec is an export-only snapshot. v2 should make it a richer, round-trip
format so a portable goal can move between tools and repos without losing intent.

### Direction

- Richer schema: phases, acceptance criteria, evidence refs, decisions, and
  blockers expressed in a stable, documented shape.
- Round-trip import: read an existing `.goals/goal-state.json` back into live
  goal state, not just write it out.
- Import an existing AGENTS.md / CLAUDE.md goal block as a starting goal so users
  can adopt Goals without restarting their work.
- Consider a JSON-LD / linked-data framing so the spec is interoperable and
  self-describing for other tools.

### Open Questions

- How much of the append-only event log belongs in the portable spec versus a
  derived snapshot?
- What is the compatibility contract when `PORTABLE_SPEC_VERSION` increments?
- Should import be strict (reject unknown fields) or lenient (preserve and warn)?

## Native loop adapters

**Status:** Forward-looking. `goals emit --agent claude|codex` exists today and
emits a transcript-verifiable native stop-condition derived from the current
phase's acceptance criteria, ready to paste into Claude `/goal` or Codex.
`goals context sync [--target agents|claude|both]` keeps a managed
`<!-- goals:context:start -->`…`end` block current in AGENTS.md and CLAUDE.md
while preserving human-written content. `goals adapter check` reports adapter
availability. For enforcement that does not depend on the transcript, an opt-in
Stop hook (`GOALS_ENFORCE=1`) decides deterministically from durable gate state,
with circuit breakers on review attempts (`GOALS_MAX_PHASE_ATTEMPTS`) and a token
budget (`GOALS_MAX_TOKENS`) — see [docs/subsystems.md](docs/subsystems.md).

The next frontier is emitting acceptance gates for more native loops so durable
goal state can drive each tool's own stop condition.

### Direction

- Aider commit gate: emit a check that gates an Aider commit on phase acceptance
  criteria.
- OpenHands check: emit a stop/verify condition OpenHands can read.
- Keep each adapter emit transcript-verifiable: the native tool should be able to
  confirm the condition from its own output, not trust a flag.
- Keep emitted conditions derived from recorded acceptance criteria so they stay
  in sync with the goal.

### Open Questions

- Which tools expose a stable enough stop-condition hook to target?
- How should emit degrade when a tool has no native gate (instructions only)?
- Should context sync support tool-specific block formats beyond AGENTS/CLAUDE?

## Evidence ledger

**Status:** Forward-looking. The goal state is already an append-only event log,
and `goals phase evidence` records proof against acceptance criteria. The
direction here is to make captured evidence stronger and harder to fake.

### Direction

- Append-only run capture: record command runs with their output as evidence
  events.
- Artifact hashes: hash referenced files/outputs so "done" is backed by content
  identity, not just a path.
- Keep the ledger portable and committable so the proof travels with the repo.

### Open Questions

- What should be hashed by default versus on request (cost and noise)?
- How large can captured run output get before it should be summarized or
  externalized?
- Should hashed artifacts be verified at review time, acceptance time, or both?

## Architecture map

**Status:** Implemented (vertical slice). `goals architecture show|brief|check|update`
exists. Goals renders a default phase-derived architecture map, accepts a typed
project-specific map, exposes a compact `architecture brief`, shows it in the
dashboard, and `architecture check` compares recorded changed files and evidence
refs against the worktree to catch stale maps.

Future depth should improve relationship inference and how conflicting maps from
parallel worktrees reconcile, without turning the map into a control plane.

### Open Questions

- Should the check infer module relationships, or only verify that recorded maps
  mention changed code?
- Should code-derived checks be blocking for technical goals by default?

## Decision brief

**Status:** Implemented (vertical slice). `goals decision brief` and
`goals decision explain` exist. The brief shows only choices that need the user,
the recommended reply, what happens after, and how many routine choices can stay
with the agent. The explainer renders Basic / Detailed / Technical levels using
active goal history.

Future depth should refine how much project history is read per decision and how
uncertainty is shown when history is incomplete or stale.

## Dashboard depth

**Status:** Partially implemented. The dashboard is a single read-only HTML file
with a Journey strip, a "how to read this page" primer, Goal Brief, Progress,
Issues, a visual Decisions timeline (who decided, and reversibility), a Memory
hierarchy (observations rolling up into preferences), Architecture, Evidence,
Sources, and Technical Details views.

Future dashboard work should deepen those views without making the dashboard a
control plane.

### Direction

- Progress: phases, current step, waiting-on, blockers, completion.
- Issues: blockers, missing proof, failed gates, state mismatches.
- Decisions: recommendation, options, risk, reversibility, suggested reply.
- Evidence: checks, acceptance criteria, known gaps, proof, and artifact hashes
  once the evidence ledger lands.
- Logs: event timeline and review attempts.

### Open Questions

- How much detail belongs in a read-only artifact before it needs interactivity?
- Should the dashboard read the portable spec so it works without live state?

## Mode B standalone runner

**Status:** Forward-looking. Today Goals is primarily a Mode A layer: it provides
durable state, evidence, registries, and native-condition emit while a native
agent owns the inner loop. A Mode B standalone runner would let Goals drive a
goal end to end on its own for environments without a native loop.

### Direction

- Run phases against recorded acceptance criteria without a host agent.
- Reuse the same evidence, checkpoint, and decision rules as Mode A.
- Keep Mode B optional so Mode A stays the primary, lock-in-free integration.

### Open Questions

- How should a standalone runner execute checks safely across project types?
- How do Mode B handoffs differ from Mode A native-agent handoffs?
- Where is the line between "runner" and "yet another agent framework"?
