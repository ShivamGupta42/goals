# Goals subsystems

Behavior reference for the durable subsystems that sit under the phase loop. For
the system diagrams and lifecycle, see [`architecture.md`](architecture.md); for
why Goals exists alongside native loops, see the root `README.md`.

## Memory loop

Goals records repeated friction, derives improvement suggestions, then syncs
sanitized lessons across similar projects:

```bash
uv run goals memory record "Repeated setup confusion" --area skill --kind friction
uv run goals memory absorb
uv run goals memory suggest
uv run goals memory sync ../similar-goals-project
```

`record` when an agent notices a reusable issue during work. `absorb` after a
goal has evidence, blockers, failed reviews, or learnings that should become
reusable memory. `suggest` surfaces an improvement only when a pattern repeats or
a gap is high severity. `sync` is a dry run by default and imports only sanitized
suggestions — raw source summaries and evidence refs stay out unless explicitly
requested.

Memory is local generated state under `.agent-workflow/self-evolution/`; it is
not meant for public commits.

The visual loop builder feeds the same loop. After a phase is accepted,
`goals loop detect <phase>` inspects its evidence and review for regressions and
records each *with evidence refs* — routed **improve-now** (blocking, surfaced)
or **defer** (recorded, awaiting approval). `goals loop improve` turns that
evidence-backed memory into a reviewable change set, and `--apply` enacts only
the safe, reversible loop-design fixes. Deferred items never auto-apply.

## Decision rule

Only **blocking** decisions are user-facing by default. The agent can decide
reversible or low-risk details itself when it records the assumption, why it is
reversible, what evidence proves the result, and how to undo it. The user sees a
question only when the answer changes safety, privacy, cost, external side
effects, data migration, or the core direction.

```bash
uv run goals decision brief
uv run goals decision explain --file decision.json --level basic|detailed|technical
```

`decision brief` is the non-technical first pass: the choices that need the user,
the recommended reply, what happens next, and how many routine choices stay with
the agent. The explainer marks which facts came from project history versus
current agent judgment, so the user can tell whether they need to be interrupted.

Checkpoints apply the same idea to phase progress. `goals checkpoint current`
shows the current validation point in plain language: what is checked, who is
waiting, what proof exists, what remains, and the next safe step. Required
checkpoints must pass or be waived before a phase can be reviewed or accepted.

## Enforced stop gate

The native `/goal` checker reads only the transcript, so "done" — and "keep
going" — are asserted, not proven. Goals ships an opt-in Stop hook that decides
deterministically from durable gate state instead. It is **off by default**; set
`GOALS_ENFORCE=1` to turn it on.

When enforced, the Stop hook blocks the agent from stopping while the current
phase still has agent work, and never traps it otherwise — a finished, failed,
paused, or blocked goal, or one waiting on the user, is always free to stop. Two
deterministic circuit breakers also hand control back instead of looping forever:

- **Review-attempt cap** — once the current phase's latest review is `BLOCKED`,
  or it has failed review `GOALS_MAX_PHASE_ATTEMPTS` times (default 3, matching
  the gate's own review-fix cap), the gate stops re-blocking. The decision keys
  off the *latest* review, so a stale failure from an earlier cycle can't trip it
  after a later pass.
- **Token budget** — set `GOALS_MAX_TOKENS` to a positive integer and the gate
  stops re-blocking once the session transcript's billed tokens reach it. A
  deterministic budget guard in *tokens, not USD*: Goals doesn't run the model
  loop, but the Stop hook is handed the session `transcript_path` and sums the
  per-call `usage` the transcript records. Opt-in with no default — any fixed
  number would arbitrarily cut off a legitimately long session.

Every signal is durable and inspectable (gate verdicts in the event log, token
usage in the transcript file); none is a transcript *judgment*. The hook is
fail-open: any unexpected error allows the stop rather than trapping the agent.
Implementation: `src/goals/agent_hooks.py` and `src/goals/token_budget.py`.
