# Self-Evolution

Goals should improve by running itself against different kinds of goals and
turning repeated friction into product changes. This document defines the
current loop.

## Evaluation Scenarios

Run the built-in scenario evaluator:

```bash
uv run goals eval scenarios --adapter claude
uv run goals eval scenarios --adapter codex
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

## End-User Experience

The decision layer and visualization layer should be judged from the user's
point of view, not from the storage model.

Decision experience means:

- only blocking or high-risk choices are surfaced to the user,
- the question is plain-language,
- options are clear,
- the reason for asking is visible,
- reversible choices can be made by the agent and recorded as assumptions.

Agents can generate a user-ready explanation from the active goal history:

```bash
uv run goals decision explain --file decision.json --level basic
uv run goals decision explain --file decision.json --level detailed
uv run goals decision explain --file decision.json --level technical
```

The explainer should include what Goals already knows from accepted phases,
evidence, checks, changed files, blockers, learnings, and prior decisions. It
should be clear about whether the user really needs to be interrupted.

Visualization experience means:

- the user can see what is happening,
- the user can see whether the goal is blocked,
- the user can see what proof exists,
- technical users can inspect details without forcing non-technical users to
  read raw JSON.

The architecture view extends this principle: the dashboard gives a simple map,
while `architecture.md` gives technical users a Markdown/Mermaid diagram they
can question. It should show what is built, planned, blocked, deferred, or
missing while keeping the default view simple.

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
- a dashboard that makes progress and blockers visible,
- decision explanations that non-technical users can understand.

Future work should connect scenario results to automatic skill/plugin selection,
and the first registry-backed version now recommends skills/plugins in Mode A
handoffs and the dashboard. Goals must still always know what phase it is in,
what evidence exists, what remains uncertain, whether a decision really needs
the user, and whether an external tool needs approval before use.
