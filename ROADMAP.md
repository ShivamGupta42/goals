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

**Status:** Implemented as a first vertical slice. Goals now renders a default phase-derived
`architecture.md`, accepts a typed project-specific architecture map, includes it
in Mode A handoffs, exposes a compact `goals architecture brief`, and shows an
Architecture section in the dashboard. `goals architecture check` compares
recorded changed code files and architecture evidence refs with the worktree so
agents can catch stale map evidence and code changes that are not represented in
the map. Parallel-worktree merge behavior is handled separately by
`goals merge-check`.

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
- Run code-derived checks before phase acceptance so changed files and
  architecture evidence stay aligned.
- Render this in the dashboard as an Architecture view beside Progress,
  Decisions, Evidence, and Technical Details.

### Why It Matters

- Non-technical users can see a simple "what is happening" view.
- Technical users can question whether the architecture matches the goal.
- Coordinators can detect mismatches between the goal, phase evidence, and actual
  implementation.
- Reviewers can see what is explicitly not built, reducing false confidence.

### Open Questions

- Should deeper architecture extraction infer relationships between modules, or
  only verify that recorded maps mention changed code?
- Should code-derived architecture checks become blocking for technical goals by
  default, or stay as a strict-mode gate chosen by the agent?
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
sync`. It can audit registries with `goals ecosystem audit` to catch vague
routing, weak descriptions, unsafe approval policy, non-portable command hints,
and missing validation hints. It now also has a permission policy registry and
`goals permission check`, so agents can tell whether a tool or action stays with
the agent, needs the user, or is unsafe without explicit approval. Plugin
discovery reads common bundle metadata such as `.codex-plugin/plugin.json`,
`manifest.json`, and `package.json`, then proposes conservative portable entries
that require review.

### Direction

- Keep registry entries portable and public-safe.
- Score skills/plugins from the objective, current phase, acceptance criteria,
  decisions, project signals, and profile hints.
- Clearly label recommendations as suggestions, not automatic external actions.
- Mark tools that need user approval because they may change remote state, cost
  money, or touch private data.
- Keep permission policies human-readable and project-overridable so
  non-technical users can understand why an agent is asking.
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
gaps, unsafe reviews, merge-readiness risks, and user-decision filtering. The
self-check roll-up now runs the evaluation matrix across Claude and Codex
adapter shapes and summarizes recommended next product slices. Goals can now
turn those slices into a dry-run `ROADMAP.md` update plan with `goals roadmap
suggest`, and `--apply` updates only a generated roadmap block. Merge readiness
now includes a parallel worktree scan that reports dirty sibling worktrees,
branch drift, overlapping files, and parallel migration-ordering risk. Ecosystem
routing can now merge multiple agents' tool recommendations into one coordinator
view with consensus ranking, conflict notes, and approval-required user
questions. Permission policy checks now give Mode A agents a simple
registry-backed way to keep local/reversible choices moving while escalating
external, costly, destructive, or production-affecting actions. Cross-project
memory sync can now inspect another Goals project or memory file, dry-run
sanitized lesson imports, and apply them to the current project's local memory
only when requested. Professional boundary templates now give Mode A agents
plain-language wording for medical, legal, financial, safety, and general
high-stakes goals, including what the agent can do, what needs the user or a
qualified professional, expected evidence, and safe next steps.

### Direction

- Record friction, gaps, learnings, and successes by area: phase, skill, gate,
  decision, dashboard, safety, docs, tests, ecosystem, and more.
- Derive suggestions only when the issue is repeated or high severity.
- Keep the memory local and ignored by default because it can include project
  history and private context.
- Use memory to recommend small improvements to skills, phases, gates, docs, or
  registries after dogfood runs.
- Use `goals memory sync PATH` when a similar Goals project already learned a
  relevant lesson; keep it dry-run-first and import sanitized suggestions only.
- Use coverage reports to spot goal families that need new scenarios, gates, or
  public product boundaries.
- Use `goals eval self-check` as the default self-evolution health report before
  and after product changes.
- Use `goals roadmap suggest` to turn self-check gaps into a reviewed, bounded
  roadmap update instead of asking agents to edit planning notes by hand.
- Use `goals ecosystem merge` when Claude, Codex, workers, or specialist agents
  recommend different tools; keep routine routing with the coordinator and only
  ask the user about approval-required tools.
- Use `goals permission check` before external connectors, destructive commands,
  paid tools, or production-affecting actions; keep the report understandable to
  non-technical users.
- Use `goals boundary explain --domain auto` before high-stakes medical, legal,
  financial, safety, or professional-judgment guidance.
- Keep temporary lifecycle rehearsal in the merge checklist so runtime behavior
  is tested, not only described.
- Keep issue stress evaluation in the merge checklist so Goals proves it can
  find bad states and avoid unnecessary user interruptions.
- Keep `goals merge-check` in coordinator merge flows so migration ordering,
  branch drift, dirty sibling worktrees, file overlap, parallel migration risk,
  and parallel-worktree reconciliation are checked before humans are asked to
  resolve only genuinely high-risk choices.

### Open Questions

- How should parallel worktree memories be reconciled?
- When should a memory suggestion become a blocking user decision instead of an
  agent-handled improvement?
- Should Goals add a separate user-wide memory registry, or keep cross-project
  sync explicit and project-selected?

## Source Evidence

**Status:** Partially implemented. Goals can record source evidence and
source-backed claims as append-only goal events, includes source prompts in Mode
A handoffs, and renders sources in the dashboard. Business scenario evaluation
now treats source evidence as a current capability. Goals can also run
`goals source citations` to check claim traceability and qualification, and
`goals source freshness` to check recorded source age against simple
type-specific freshness windows. Routine citation and freshness cleanup stays
with the agent as repair work, while weak or stale high-stakes evidence can
become a user-facing decision.

### Direction

- Record sources for research, business, customer, market, migration, safety, and
  architecture claims.
- Keep source evidence readable for non-technical users: title, locator, type,
  summary, credibility, claim, and confidence.
- Check citation quality before relying on claims: missing source ids, missing
  locators or summaries, low-confidence claims, absolute wording, and
  high-confidence claims backed only by low-credibility sources.
- Let phase evidence reference `source_ids` so proof and claims connect.
- Later, add richer provenance and optional external source refresh adapters.

### Open Questions

- Should external URLs be fetched and archived, or kept as user-provided
  locators only?
- Which projects need stricter source freshness windows than the built-in
  defaults?
- Should business/research goals have a stronger source gate than code goals?
- Should citation quality thresholds be configurable by project or goal domain?

## Asset Provenance

**Status:** First vertical slices implemented. Goals can record generated,
external, stock, derived, user-provided, or other assets as append-only goal
events, include asset summaries in Mode A handoffs, check provenance with
`goals asset provenance`, compare creative directions with
`goals creative compare`, add findings to `goals issues`, and render recorded
assets and variants in the dashboard.

### Direction

- Keep creative and publishing workflows safe without making every taste choice
  a user decision.
- Treat missing asset metadata as agent repair work: stable locator, generation
  tool, sanitized prompt, source ids, license, and usage-rights status.
- Surface restricted or blocked usage rights as plain-language user questions.
- Keep provenance portable by rejecting local machine paths in asset locators.
- Next, add richer source-to-asset lineage and optional external rights
  verification adapters.

### Open Questions

- Should Goals provide project-specific asset type presets for design, video,
  research data, and document workflows?
- Should generated prompts be stored verbatim, summarized, or policy-sanitized
  by default?
- When should asset provenance become a blocking gate instead of an issue report?

<!-- goals:self-check-roadmap:start -->
## Goals Self-Check Suggestions

This generated section is safe to refresh. It turns self-check findings into roadmap candidates without changing human-written roadmap notes.

- **Handoff Owner Registry** (`p1`)
  - Source: self-check
  - Capability: `handoff_owner_registry`
  - Why: Self-check recommends handoff owner registry as a next product capability that would make Goals better at finishing broad goals.
  - Recommended change: Define the smallest user-visible handoff owner registry slice, add self-check coverage, and keep any write behavior dry-run-first until reviewed.
  - Evidence: `self-check.next_slices[0]`, `self-check.summary`
- **Mandatory External Review Gate** (`p2`)
  - Source: self-check
  - Capability: `mandatory_external_review_gate`
  - Why: Self-check recommends mandatory external review gate as a next product capability that would make Goals better at finishing broad goals.
  - Recommended change: Define the smallest user-visible mandatory external review gate slice, add self-check coverage, and keep any write behavior dry-run-first until reviewed.
  - Evidence: `self-check.next_slices[1]`, `self-check.summary`
- **Optional Calendar Context** (`p2`)
  - Source: self-check
  - Capability: `optional_calendar_context`
  - Why: Self-check recommends optional calendar context as a next product capability that would make Goals better at finishing broad goals.
  - Recommended change: Define the smallest user-visible optional calendar context slice, add self-check coverage, and keep any write behavior dry-run-first until reviewed.
  - Evidence: `self-check.next_slices[2]`, `self-check.summary`
- **Private Memory Boundary** (`p2`)
  - Source: self-check
  - Capability: `private_memory_boundary`
  - Why: Self-check recommends private memory boundary as a next product capability that would make Goals better at finishing broad goals.
  - Recommended change: Define the smallest user-visible private memory boundary slice, add self-check coverage, and keep any write behavior dry-run-first until reviewed.
  - Evidence: `self-check.next_slices[3]`, `self-check.summary`
- **Recurring Goal Templates** (`p2`)
  - Source: self-check
  - Capability: `recurring_goal_templates`
  - Why: Self-check recommends recurring goal templates as a next product capability that would make Goals better at finishing broad goals.
  - Recommended change: Define the smallest user-visible recurring goal templates slice, add self-check coverage, and keep any write behavior dry-run-first until reviewed.
  - Evidence: `self-check.next_slices[4]`, `self-check.summary`
<!-- goals:self-check-roadmap:end -->
