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
uv run goals brief
uv run goals issues
uv run goals merge-check
uv run goals run --adapter codex
uv run goals dashboard
uv run goals architecture show
uv run goals architecture brief
uv run goals decision brief
uv run goals boundary explain --domain auto
uv run goals ecosystem recommend
uv run goals ecosystem merge
uv run goals ecosystem discover
uv run goals ecosystem sync
uv run goals permission check github --kind plugin --action "inspect a remote issue"
uv run goals source citations
uv run goals source freshness
uv run goals source list
uv run goals asset provenance
uv run goals asset list
uv run goals memory suggest
uv run goals memory sync ../similar-goals-project
uv run goals eval scenarios --adapter claude
uv run goals eval dogfood --adapter claude
uv run goals eval coverage --adapter claude
uv run goals eval rehearsal --adapter claude
uv run goals eval issue-stress --adapter claude
uv run goals eval self-check
uv run goals roadmap suggest
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
uv run goals brief
uv run goals decision brief
uv run goals decision explain --file decision.json --level basic
uv run goals boundary explain --domain auto
```

For medical, legal, financial, safety, or similar high-stakes goals, agents can
use `goals boundary explain` to get simple wording for what the agent can do,
what needs the user or a qualified professional, what evidence is expected, and
which next steps are safe to take.

`brief` is the first non-technical view. It answers: what is happening, what
needs your answer, what the agent can do next, what proof exists, and what
technical details are available if someone wants to inspect them.

`decision brief` answers the simple end-user question: what needs my answer,
what does Goals recommend, what should I reply, what happens next, and how many
routine choices can stay with the agent. The dashboard shows the same brief,
then turns important decisions into plain-language cards with the recommendation,
options, risk, reversibility, confidence, known context, and a suggested reply.
Routine reversible choices stay with the agent.

Agents can ask Goals what could block the current goal before interrupting the
user:

```bash
uv run goals brief
uv run goals issues
uv run goals merge-check
```

The goal brief gives the user-safe summary. The issue report checks missing
proof, failed gates, unresolved source claims, important decisions, blockers,
and state mismatches. By default it is a read-only report; use `--strict` when a
script should fail on blocking issues.

`merge-check` is the coordinator's pre-merge view. It looks for migration files
without recorded ordering proof, scans sibling worktrees when Git exposes them,
checks dirty workers, branch drift, file overlap, parallel migration risk,
base-branch or conflict risks, and high-risk merge choices that really need the
user. Routine merge cleanup stays as an agent action.

Agents can record source evidence for research, business, customer, market, or
technical claims:

```bash
uv run goals source add "Customer interview" \
  --locator "interview-001" \
  --source-type interview \
  --claim "Users need plain-language progress." \
  --confidence 0.8
uv run goals source citations
uv run goals source freshness
uv run goals source list
```

`source citations` checks whether source-backed claims are traceable and
appropriately qualified. It catches claims with no source, missing source ids,
missing source locators or summaries, absolute wording, low confidence, and
high-confidence claims that rely only on low-credibility sources. Most citation
cleanup stays with the agent. Weak citation evidence for high-stakes claims can
become a simple user-facing decision before the agent relies on it.

`source freshness` checks whether recorded sources are recent enough for the
claims that rely on them. Stale sources are normally agent repair work: refresh,
replace, or mark them stale. For high-stakes goals such as medical, legal,
financial, production, privacy, or safety work, stale high-confidence evidence
can become a simple user-facing decision before the agent relies on it.

Agents can record asset provenance for creative, product, document, data, or
publishing work:

```bash
uv run goals asset add "Hero image" \
  --locator "assets/hero.png" \
  --asset-type image \
  --origin generated \
  --creator-tool image-model \
  --usage-rights allowed \
  --prompt "Simple product hero"
uv run goals asset provenance
uv run goals asset list
```

`asset provenance` checks whether recorded assets have enough information to be
used safely: a stable locator, rights or license details when needed, source
links for derived assets, generated-asset prompts, and no local machine paths.
Most gaps stay as agent repair work. Restricted or blocked rights become simple
user-facing questions because they can change whether the asset may be used.

Agents can also ask Goals which skills or plugins fit the current phase:

```bash
uv run goals ecosystem recommend
uv run goals ecosystem merge
uv run goals ecosystem discover
uv run goals ecosystem sync
uv run goals ecosystem audit
```

Mode A handoffs include these recommendations automatically. Goals does not run
external tools for the agent; it explains what looks relevant and whether user
approval is needed. `ecosystem merge` combines recommendations from multiple
agents into one coordinator view, deduplicates consensus picks, keeps routine
routing with the agent, and surfaces approval-required tools as plain user
questions. Discovery inspects local skills/plugins/adapters and suggests portable
registry additions without printing local filesystem paths by default. Sync is a
dry run unless `--apply` is passed. Audit checks whether registry entries are
specific, safe, portable, and useful enough for automatic routing.

Agents can check whether a tool or action should stay with the agent, ask the
user, or stop as unsafe:

```bash
uv run goals permission check github --kind plugin --action "inspect a remote issue"
uv run goals permission check cleanup-script --kind command --action "delete production data"
```

Permission policies live in `registries/permissions.yml`. If a project does not
define one, Goals uses built-in conservative defaults. The report is written for
agents and non-technical users: what needs the user, what the agent can do, and
which policy made the call.

Agents can record repeated friction so future goals improve:

```bash
uv run goals memory record "Repeated setup confusion" --area skill --kind friction
uv run goals memory suggest
uv run goals memory sync ../similar-goals-project
```

Self-evolution memory is local generated state under `.agent-workflow/` and is
ignored by default. `memory sync` is a dry run by default: it reads another
Goals project or memory file, turns actionable lessons into sanitized
suggestions, and imports them only when rerun with `--apply`. Use
`--include-private` only when you explicitly want source summaries and evidence
references copied into the current project's local memory.

Agents can also run the full self-evolution matrix in one command:

```bash
uv run goals eval self-check
uv run goals roadmap suggest
```

`self-check` runs the scenario, dogfood, coverage, lifecycle rehearsal, and
issue-stress suites for Claude and Codex adapter shapes, then summarizes current
coverage, user-decision burden, agent repair actions, ecosystem signals, and the
next product slices worth exploring.

`roadmap suggest` turns those next slices into a dry-run `ROADMAP.md` update
plan. It writes only a generated block when `--apply` is passed, so agents can
propose self-evolution work without rewriting human roadmap notes.

Agents and technical reviewers can inspect a goal-level architecture map:

```bash
uv run goals architecture show
uv run goals architecture brief
uv run goals architecture update --file architecture.json
```

The dashboard is the simple status view for end users. `architecture brief`
summarizes what is built, what lacks evidence, what is blocked, and what to
review next. `architecture.md` is the deeper Markdown/Mermaid view for people
who want to question what is built, planned, blocked, or deferred.

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
uv run goals eval dogfood --adapter claude
uv run goals eval coverage --adapter claude
uv run goals eval rehearsal --adapter claude
uv run goals eval issue-stress --adapter claude
```

`eval dogfood` prints a plain-language report for each synthetic goal type:
what the user sees, what the agent can decide, what proof is required, and which
gaps would block the goal.

`eval coverage` checks a broader use-case matrix across personal, technical,
business, research, creative, operations, high-stakes, ecosystem, and
self-evolution goals. It separates current coverage from planned future
capabilities.

`eval rehearsal` creates temporary Git repositories and runs representative
Goals lifecycles through evidence, issue discovery, review, acceptance, and
dashboard rendering. It proves the workflow machinery can execute, not just
describe, the goal loop.

`eval issue-stress` injects broken goal states and checks whether Goals finds
missing proof, failed gates, source gaps, architecture questions, unsafe reviews,
and high-impact user decisions while keeping routine repair work with the agent.

See [docs/SELF_EVOLUTION.md](docs/SELF_EVOLUTION.md) for the current loop.
