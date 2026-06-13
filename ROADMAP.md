# Roadmap

This file tracks larger product directions that are intentionally not being built
yet. Roadmap entries should explain the user value, the likely shape, and the
questions to resolve before implementation.

## Decision Explainer V2

**Status:** Partially implemented. Basic/Detailed/Technical rendering, active
goal history context, and a compact `goals decision brief` read model exist;
richer memory limits are still planned. The dashboard now filters routine
decisions, shows a non-technical decision brief, and shows important user-facing
decision cards with recommendation, options, risk, reversibility, confidence,
known context, uncertainty, and technical evidence.

Goals should help agents explain technical decisions in a way non-technical users
can understand, while still giving technical users enough detail to challenge the
work. Some decisions cannot be explained from the current prompt alone; the agent
may need to understand what has already happened in the project.

### Direction

- Use project history as context: prior goal events, accepted phases, evidence,
  decisions, blockers, learnings, changed files, and dashboard summaries.
- Add a "what we know so far" section to each decision explanation.
- Keep a compact decision brief for non-technical users before deeper detail.
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

**Status:** Partially implemented. Goals now renders a default phase-derived
`architecture.md`, accepts a typed project-specific architecture map, includes it
in Mode A handoffs, exposes a compact `goals architecture brief`, and shows an
Architecture section in the dashboard. Deeper code-derived validation and
parallel-worktree merge behavior are still planned.

For larger goals, technical users need a way to inspect what is being built,
what is not built yet, and how each phase changes the project. Goals should
optionally maintain a goal-level architecture map alongside the normal progress
state.

### Direction

- Maintain an optional Markdown artifact at
  `.agent-workflow/goals/<goal-id>/architecture.md`.
- Let agents record one typed architecture diagram for the entire goal, updated
  as the goal evolves.
- Prefer Mermaid in Markdown for portability, with room for generated HTML later.
- Track modules, files, data flow, external systems, and status labels such as
  planned, in progress, built, deferred, or removed.
- Link each architecture node to phases, decisions, evidence, or changed files
  when possible.
- Keep a compact architecture brief with status counts, evidence gaps, open
  questions, and review focus.
- Render this in the dashboard as an Architecture view beside Progress,
  Decisions, Evidence, and Technical Details.

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

## Dashboard Views

**Status:** Partially implemented. The dashboard now includes Goal Brief, Progress, Issues,
Decisions, Skills & Plugins, Memory, Architecture, Evidence, Sources, and
Technical Details as read-only views.

The dashboard is still a single read-only HTML file. Future dashboard work
should deepen those views without making it a control plane.

Likely views:

- Progress: phases, current step, waiting-on, blockers, and completion.
- Goal Brief: plain-language summary of what needs the user, what the agent can
  do next, and what proof exists.
- Issues: blockers, missing proof, unresolved claims, failed gates, and state
  mismatches.
- Decisions: explanations, recommended option, alternatives, risk, and suggested
  reply.
- Architecture: optional goal architecture map and build status.
- Evidence: checks, acceptance criteria, known gaps, and proof.
- Logs: event timeline and review attempts.
- Technical Details: goal id, event offset, source commit, paths, and adapter.

## Ecosystem Routing

**Status:** Partially implemented. Goals can recommend skills and plugins from
portable YAML registries, includes those recommendations in Mode A handoffs and
the dashboard, can discover local skills/plugins/adapters with `goals ecosystem
discover`, and can plan/apply reviewed registry additions with `goals ecosystem
sync`. It can also audit registries with `goals ecosystem audit` to catch vague
routing, weak descriptions, unsafe approval policy, non-portable command hints,
and missing validation hints. Plugin discovery reads common bundle metadata such as
`.codex-plugin/plugin.json`, `manifest.json`, and `package.json`, then proposes
conservative portable entries that require review.

### Direction

- Keep registry entries portable and public-safe.
- Score skills/plugins from the objective, current phase, acceptance criteria,
  decisions, project signals, and profile hints.
- Clearly label recommendations as suggestions, not automatic external actions.
- Mark tools that need user approval because they may change remote state, cost
  money, or touch private data.
- Expand local discovery adapters as Claude/Codex and local AI toolchains add
  new plugin metadata formats.
- Suggest portable registry additions for local tools that are missing from the
  repo registries.
- Keep registry sync as a dry run by default, with explicit `--apply` after
  review.
- Use SkillOpt-style validation gates for deeper future skill improvement:
  collect scored rollouts, propose bounded edits, and accept only improvements
  that pass held-out validation.

### Open Questions

- How should conflicting skill recommendations from different agents be merged?
- How much should Goals learn from repeated recommendation misses across goals?
- Which plugin metadata files should Goals trust across Claude, Codex, and local
  AI toolchains?

## Self-Evolution Memory

**Status:** Partially implemented. Goals now stores local self-evolution memory
under `.agent-workflow/self-evolution/memory.json`, derives suggestions from
repeated friction or high-severity gaps, includes those suggestions in Mode A
handoffs, shows visible suggestions in the dashboard, and can run a synthetic
dogfood report across personal, technical, business, self-evolution, and
ecosystem goal types. It also has a broader use-case coverage matrix for
personal, technical, business, research, creative, operations, high-stakes,
ecosystem, and self-evolution goals. Lifecycle rehearsal now creates temporary
Git repositories and drives representative goals through evidence, issue
discovery, review, acceptance, and dashboard rendering. Issue stress evaluation
now injects broken goal states to verify missing proof, failed gates, source
gaps, unsafe reviews, merge-readiness risks, and user-decision filtering.

### Direction

- Record friction, gaps, learnings, and successes by area: phase, skill, gate,
  decision, dashboard, safety, docs, tests, ecosystem, and more.
- Derive suggestions only when the issue is repeated or high severity.
- Keep the memory local and ignored by default because it can include project
  history and private context.
- Use memory to recommend small improvements to skills, phases, gates, docs, or
  registries after dogfood runs.
- Use coverage reports to spot goal families that need new scenarios, gates, or
  public product boundaries.
- Keep temporary lifecycle rehearsal in the merge checklist so runtime behavior
  is tested, not only described.
- Keep issue stress evaluation in the merge checklist so Goals proves it can
  find bad states and avoid unnecessary user interruptions.
- Keep `goals merge-check` in coordinator merge flows so migration ordering,
  branch drift, and parallel-worktree reconciliation are checked before humans
  are asked to resolve only genuinely high-risk choices.

### Open Questions

- Should memory remain project-local, or support an optional user-wide memory?
- How should parallel worktree memories be reconciled?
- When should a memory suggestion become a blocking user decision instead of an
  agent-handled improvement?

## Source Evidence

**Status:** Partially implemented. Goals can record source evidence and
source-backed claims as append-only goal events, includes source prompts in Mode
A handoffs, and renders sources in the dashboard. Business scenario evaluation
now treats source evidence as a current capability.

### Direction

- Record sources for research, business, customer, market, migration, safety, and
  architecture claims.
- Keep source evidence readable for non-technical users: title, locator, type,
  summary, credibility, claim, and confidence.
- Let phase evidence reference `source_ids` so proof and claims connect.
- Later, add richer provenance, source freshness, and citation quality checks.

### Open Questions

- Should external URLs be fetched and archived, or kept as user-provided
  locators only?
- How should Goals warn about stale or low-credibility sources?
- Should business/research goals have a stronger source gate than code goals?
