# Self-Evolution

Goals should improve by running itself against different kinds of goals and
turning repeated friction into product changes. This document defines the
current loop.

## Evaluation Scenarios

Run the built-in scenario evaluator:

```bash
uv run goals eval scenarios --adapter claude
uv run goals eval scenarios --adapter codex
uv run goals eval dogfood --adapter claude
uv run goals eval coverage --adapter claude
uv run goals eval rehearsal --adapter claude
uv run goals eval issue-stress --adapter claude
uv run goals eval self-check
uv run goals roadmap suggest
```

The evaluator dry-runs Goals against five scenario families:

- Personal: private, reversible life goals where the agent should surface only
  safety or preference decisions that matter.
- Technical: repository changes where worktrees, evidence, checks, and review
  gates matter.
- Business: research and planning goals where source evidence and audience
  decisions matter.
- Self-evolution: Goals improving itself after dogfood runs.
- Ecosystem: Claude/Codex skills, plugins, adapters, and registries helping the
  agent choose tools without making the user manually route every step.

Each scenario has required current capabilities and planned future capabilities.
The command fails when current capabilities are missing, but planned
capabilities remain visible as the next frontier.

`eval dogfood` uses the same scenarios to produce a plain-language report. It
checks whether each synthetic goal keeps user decisions small, documents what
the agent can decide without interrupting the user, and names the proof required
to accept the goal. This is the quick self-evolution check before and after
larger product changes.

`eval coverage` checks a wider matrix of representative goal families:
personal, technical, business, research, creative, operations, high-stakes,
ecosystem, and self-evolution. It shows which current capabilities cover each
family and which planned capabilities should become future product work.

`eval rehearsal` creates temporary Git repositories and actually runs
representative Goals lifecycles. It records evidence, checks issues, reviews and
accepts phases, and renders dashboards so self-evolution work is tested against
runtime behavior, not only static scenario descriptions.

`eval issue-stress` injects broken goal states and checks whether Goals catches
missing proof, failed gates, unresolved source claims, architecture questions,
unsafe reviews, and high-impact user decisions. It also verifies that routine
repair work stays with the agent instead of becoming unnecessary user prompts.

`eval self-check` runs the full matrix for Claude and Codex adapter shapes and
summarizes whether Goals is meeting its original promise. It is the first
command to run during self-evolution work; the individual eval commands are
drill-down views when the roll-up finds a gap or a promising next slice.

`roadmap suggest` turns the self-check's next slices into a dry-run roadmap
update plan. It is safe for agents to run before asking the user what to build
next: the default output is a preview, and `--apply` only updates a bounded
generated block in `ROADMAP.md`.

## Ecosystem Discovery

Goals can inspect local skill roots, plugin roots, and adapter executables:

```bash
uv run goals ecosystem recommend
uv run goals ecosystem merge
uv run goals ecosystem discover
uv run goals ecosystem sync
uv run goals ecosystem audit
uv run goals permission check github --kind plugin --action "inspect a remote issue"
```

`recommend` uses portable registries to route the current phase. `merge`
combines recommendations from multiple agents or adapter shapes into one
coordinator view. It ranks consensus, records command-hint disagreements as
agent-side routing work, and only asks the user about approval-required tools.
`discover` looks at local `SKILL.md` files, common plugin metadata files, and
Claude/Codex adapter availability, then suggests registry additions for tools
that are present locally but missing from the repo. Discovery output is sanitized
by default; it labels sources without printing local filesystem paths. `sync`
turns those suggestions into a reviewed registry update plan; it is a dry run
unless `--apply` is passed. `audit` checks whether registry entries are specific
enough to route, safe enough for handoff prompts, and ready for validation-gated
self-evolution.

`permission check` answers a narrower question before the agent uses a tool or
action: can this stay with the agent, should the user approve it, or is it unsafe
without explicit approval? Project policies live in `registries/permissions.yml`;
without a project policy, Goals uses built-in conservative defaults for local,
external, destructive, costly, and production-affecting work.

## Memory Loop

Goals can record repeated friction and derive improvement suggestions:

```bash
uv run goals memory record "Repeated setup confusion" --area skill --kind friction
uv run goals memory absorb
uv run goals memory suggest
uv run goals memory sync ../similar-goals-project
```

Use `record` when an agent notices a reusable issue during work. Use `absorb`
after a goal has evidence, blockers, failed reviews, or learnings that should
become reusable memory. Suggestions are surfaced when a pattern repeats or a gap
is high severity.

Use `memory sync` when another Goals project has already exposed useful
friction. It is a dry run by default and imports only sanitized suggestions with
`--apply`; raw source summaries and evidence refs stay out unless
`--include-private` is explicitly used.

Memory is local generated state under `.agent-workflow/self-evolution/`. It is
not meant for public commits.

## Professional Boundaries

High-stakes goals need clear limits in plain language. Agents can run:

```bash
uv run goals boundary explain --domain auto
```

The report explains what the agent can safely do, what needs the user or a
qualified professional, what evidence should be recorded, and suggested wording
for medical, legal, financial, safety, or general professional judgment
boundaries.

## Source Evidence

Research and business goals need proof that is easy to inspect. Agents can
record sources and source-backed claims:

```bash
uv run goals source add "Customer interview" \
  --locator "interview-001" \
  --source-type interview \
  --claim "Users need plain-language progress." \
  --confidence 0.8
uv run goals source freshness
uv run goals source list
```

Mode A prompts include source summaries and ask agents to record sources when a
phase makes customer, market, research, architecture, migration, or safety
claims. `source freshness` checks source age against simple, type-specific
freshness windows before an agent relies on claims. The dashboard shows recorded
sources, claims, and freshness status separately from code checks.

## End-User Experience

The decision layer and visualization layer should be judged from the user's
point of view, not from the storage model.

Agents should run the issue report before escalating:

```bash
uv run goals brief
uv run goals issues
uv run goals merge-check
```

The brief is the non-technical first pass: what is happening, what needs the
user, what the agent can do next, and what proof exists. Agents should use this
wording when they interrupt the user. The issue report separates important user
questions from agent-side repair actions. It is meant to help agents discover
blockers, missing proof, failed reviews, unresolved source claims, and state
mismatches before asking the user for help. The issue stress evaluator keeps
this promise honest by testing both sides: what should be surfaced to the user
and what the agent should repair itself.

`merge-check` is the coordinator pass before merging. It is designed for
technical users and non-technical project owners: it explains whether migration
ordering, branch drift, parallel worktree reconciliation, dirty sibling
worktrees, overlapping files, parallel migration changes, or high-risk merge
approval is still unresolved, and it keeps routine repair work with the agent.

Decision experience means:

- only blocking or high-risk choices are surfaced to the user,
- the question is plain-language,
- options are clear,
- the reason for asking is visible,
- reversible choices can be made by the agent and recorded as assumptions.

Agents can generate a user-ready explanation from the active goal history:

```bash
uv run goals decision brief
uv run goals decision explain --file decision.json --level basic
uv run goals decision explain --file decision.json --level detailed
uv run goals decision explain --file decision.json --level technical
```

`decision brief` is the non-technical first pass: it shows only choices that
need the user, the recommended reply, what happens after the reply, and how many
routine choices can stay with the agent.

The explainer should include what Goals already knows from accepted phases,
evidence, checks, changed files, blockers, learnings, and prior decisions. It
should be clear about whether the user really needs to be interrupted.
The dashboard shows the same principle as readable decision cards: important
choices include recommendation, options, risk, reversibility, confidence, known
context, uncertainty, and a suggested reply, while routine reversible choices
stay with the agent.

Visualization experience means:

- the user can see what is happening,
- the user can see whether the goal is blocked,
- the user can see what issue needs attention,
- the user can see what proof exists,
- technical users can inspect details without forcing non-technical users to
  read raw JSON.

The architecture view extends this principle: the dashboard gives a simple map
and a compact architecture brief, while `architecture.md` gives technical users
a Markdown/Mermaid diagram they can question. It should show what is built,
planned, blocked, deferred, missing, and not yet backed by evidence while
keeping the default view simple.

## Decision Rule

Goals should not ask the user about every choice. The scenario evaluator treats
only `blocking` decisions as user-facing by default.

The agent can decide reversible or low-risk details itself when it records:

- the assumption it made,
- why it is reversible,
- what evidence proves the result,
- how to undo or change direction later.

The user should see a simple question only when the answer changes safety,
privacy, cost, external side effects, data migration, or the core direction of
the goal.

## Ecosystem Fit

Claude Code and Codex already provide native loops, skills, plugins, tools, and
permissions. Goals should not replace them. Its unique value is to provide:

- durable goal state across turns,
- phase evidence and review gates,
- adapter-aware native `/goal` instructions,
- registries for skills, gates, agents, profiles, and adapters,
- permission policies that keep routine tool choices with agents while surfacing
  external, costly, or destructive actions,
- source freshness checks that keep stale evidence as agent repair work unless
  a high-stakes claim really needs the user,
- a dashboard that makes progress and blockers visible,
- decision explanations that non-technical users can understand.

Future work should connect scenario results to automatic skill/plugin selection,
and the first registry-backed version now recommends skills/plugins in Mode A
handoffs and the dashboard. Local discovery can compare installed skills,
plugins, and adapters with portable registries. Self-evolution memory records
repeated friction and turns it into improvement suggestions. Source evidence
records what claims are backed by which sources. Goals must still always know
what phase it is in, what evidence exists, what remains uncertain, whether a
decision really needs the user, and whether an external tool needs approval
before use.
