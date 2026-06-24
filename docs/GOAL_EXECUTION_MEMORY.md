# Goal-execution memory

A tiny, private, **human-editable** memory that learns how you like goals run, so Goals
auto-executes better over time — without inventing reasons or over-generalizing.

It lives in two plain-Markdown files under `~/.goals/user/` (override the root with
`GOALS_HOME`). Both are yours to read, edit, reorder, or delete by hand.

```
~/.goals/user/
├── preferences.md    # YOU own it. Durable preferences that steer auto-execution.
└── observations.md   # Agent-owned, append-only. Situated decisions, one per line.
```

Nothing under here is JSON — it is all editable Markdown. The only bookkeeping (which
goals already showed the post-goal prompt, so you are not asked twice) is stored as
inert HTML-comment markers in `observations.md` — invisible when the Markdown is
rendered, and ignored when the log is parsed.

## The model: situated observations, not causal rules

A decision is recorded as **what** you chose plus the observable **context** — never an
inferred cause.

```
- 2026-06-24 · goal:add-auth · [risk] chose: a local file over a database — when: throwaway prototype (you said: "no server to manage")
```

- **`chose`** — what was decided.
- **`when`** — the observable context the decision was made in.
- **`you said`** — present only when *you* gave a reason, in your own words.

There is deliberately **no "because" the agent makes up.** A reason appears only when you
state one (`provenance: stated`); otherwise the observation is just choice + context
(`provenance: observed`).

### Why no fabricated "because"

People are poor at reporting *why* they chose something. Choice-blindness and
confabulation studies show people will confidently explain choices they didn't even make
([Johansson et al. 2006](https://www.lucs.lu.se/fileadmin/user_upload/lucs/2011/01/Johansson-et-al.-2006-How-Something-Can-Be-Said-About-Telling-More-Than-We-Can-Know.pdf);
[Oxford, Neuroscience of Consciousness 2021](https://academic.oup.com/nc/article/2021/1/niab004/6166135)),
and behavioral economics finds *revealed* preference (what you did) more reliable than
*stated* preference (what you say about why)
([CEPR](https://cepr.org/voxeu/columns/reported-preference-versus-revealed-preference)).
Asking a model to infer the cause manufactures a plausible-but-false rationale, which
then misleads future goals. So we record the context (reliable) and keep the reason only
when it genuinely comes from you.

## Two tiers: observation → preference

| | Observation | Preference |
|---|---|---|
| Where | `observations.md` | `preferences.md` |
| Scope | one goal | all future goals |
| Steers auto-execution? | no | yes |
| Created by | the agent, automatically | you (stated/confirmed) |

An **observation** never silently becomes a rule. It is promoted to a **preference** only
when you state it (`goals user record`), confirm it in the post-goal interview, or
explicitly promote a recurring pattern. This is the guard against over-generalizing a
context-specific choice into a global rule — the well-documented failure mode of
auto-memory ("if you tell the model a one-off style rule, it generalizes it"). Leading
tools use the same discipline: Anthropic writes a durable rule only when a correction
repeats; Cursor requires you to approve a memory before it is saved.

At goal end, Goals surfaces a digest: this goal's observations, any choice seen across
**≥2 distinct goals** (offered for promotion), and the preferences currently in effect.

## Why Markdown, and the human/agent split

You must be able to edit this by hand, so it is Markdown, not JSON. (JSON is hostile to
hand-editing; every leading coding agent — CLAUDE.md, Cursor `.mdc`, Copilot
instructions, `AGENTS.md` — stores human-edited memory as Markdown.)

To keep your edits safe while the agent also writes, ownership is split:

- The agent **only appends** to `observations.md` (one line per decision — clean diffs,
  trivially `git revert`-able).
- The agent **never rewrites `preferences.md`**; it only inserts a bullet when you record
  or confirm one. Everything else in that file is yours and is preserved untouched.

## Commands

```bash
goals user show                              # combined human-readable view (--json for raw)
goals user digest [--goal current]           # the goal-end reflection, on demand
goals user record "<preference>" --area communication   # add a standing preference
goals user interview --goal <id> -a "..." -a "..." -a "..."   # post-goal interview → preferences
goals user import-insights --file -          # import a Claude /insights summary as preferences
goals user forget "<text>"                   # remove a matching preference (or just edit the file)
goals user forget --all [--purge]            # clear all preferences (purge deletes the files)
```

Areas: `risk`, `communication`, `workflow`, `technical`, `decision`, `other`.

## How it plugs into a goal

- **During a goal**, only confirmed `preferences.md` entries are injected as
  personalization (how decisions get surfaced/explained). Observations never leak across
  goals.
- **Recording a decision** (`goals decision record …`, or the agent's own judgement log)
  appends a situated observation — context, not cause.
- **At goal end** (`goals phase accept` on completion, and `goals finish`), the digest is
  shown and the post-goal interview is offered.

## Design sources

The model follows the agent-memory literature: separate **episodic** (timestamped,
scoped observations) from **semantic** (durable preferences), promote with
**corroboration + human confirmation**, and keep memory **editable and revertible**. Key
references: Generative Agents (memory stream + reflection), MemGPT/Letta, A-MEM, Mem0
(ADD/UPDATE/DELETE consolidation), user-modeling surveys on stated/observed/inferred
provenance, and the choice-blindness/confabulation work above.
