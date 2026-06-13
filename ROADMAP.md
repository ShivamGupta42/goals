# Roadmap

This file tracks larger product directions that are intentionally not being built
yet. Roadmap entries should explain the user value, the likely shape, and the
questions to resolve before implementation.

## Decision Explainer V2

**Status:** Planned, not implemented.

Goals should help agents explain technical decisions in a way non-technical users
can understand, while still giving technical users enough detail to challenge the
work. Some decisions cannot be explained from the current prompt alone; the agent
may need to understand what has already happened in the project.

### Direction

- Use project history as context: prior goal events, accepted phases, evidence,
  decisions, blockers, learnings, changed files, and dashboard summaries.
- Add a "what we know so far" section to each decision explanation.
- Keep three levels: Basic, Detailed, and Technical.
- Include recommendation, options, tradeoffs, risks, reversibility, confidence,
  and suggested replies or commands.
- Make the explainer clear about which facts came from project history and which
  are current agent judgment.

### Open Questions

- How much history should an agent read before a decision becomes too expensive?
- Should decision context come from raw events, derived snapshots, or a separate
  decision read model?
- How should Goals show uncertainty when project history is incomplete or stale?

## Goal Architecture Map

**Status:** Planned, not implemented.

For larger goals, technical users need a way to inspect what is being built,
what is not built yet, and how each phase changes the project. Goals should
optionally maintain a goal-level architecture map alongside the normal progress
state.

### Direction

- Add an optional Markdown artifact, for example
  `.agent-workflow/goals/<goal-id>/architecture.md`.
- Let agents record one architecture diagram for the entire goal, updated as the
  goal evolves.
- Prefer Mermaid in Markdown for portability, with room for generated HTML later.
- Track modules, files, data flow, external systems, and status labels such as
  planned, in progress, built, deferred, or removed.
- Link each architecture node to phases, decisions, evidence, or changed files
  when possible.
- Render this in the dashboard as an optional Architecture tab/view beside:
  Progress, Decisions, Evidence, Logs, and Technical Details.

### Why It Matters

- Non-technical users can see a simple "what is happening" view.
- Technical users can question whether the architecture matches the goal.
- Coordinators can detect mismatches between the goal, phase evidence, and actual
  implementation.
- Reviewers can see what is explicitly not built, reducing false confidence.

### Open Questions

- Should the architecture map be hand-authored by the agent, derived from code
  scans, or both?
- Should Goals validate the diagram against changed files or keep it advisory?
- How should conflicting diagrams from parallel worktrees be merged?

## Dashboard Tabs

**Status:** Planned, not implemented.

The current dashboard is a single read-only status page. Future dashboard work
should split the page into clear views without making it a control plane.

Likely views:

- Progress: phases, current step, waiting-on, blockers, and completion.
- Decisions: explanations, recommended option, alternatives, risk, and suggested
  reply.
- Architecture: optional goal architecture map and build status.
- Evidence: checks, acceptance criteria, known gaps, and proof.
- Logs: event timeline and review attempts.
- Technical Details: goal id, event offset, source commit, paths, and adapter.
