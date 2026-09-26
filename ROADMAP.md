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

## Discovery as first-class durable state

**Status:** Implemented (build steps 1–5, 2026-09-26). Step 1 ships in PR #43;
steps 2–5 are stacked on it and must merge **after** step 1 has been released
(`install.sh` installs from `main`), or an older CLI appending to a new log would
delete the new event types. Phase one — understanding the user before building —
runs as the `goals-discovery` skill, `/goals:discover`, and step 2 of
`/goals:create`: pain points (`goals assess pain`), desired properties with how
each is proven (`goals assess want --proof auto|user`), open questions
(`goals assess breakdown`), the approach (`goals decision record --by agent`,
then `--by user` once confirmed), and an `understanding` checkpoint only the
user's recorded reply can close. `goals assess revise` starts it over mid-goal.
The dashboard shows "What you want / What hurts today" and "Your replies on
record"; `DISCOVERY.md` is generated from the log next to the dashboard.

**Known limitations** (accepted or deferred, from the build reviews):
- Deliberate forgery is out of scope (see Threat model): an agent that hand-writes
  the host's hook payload (`hook_event_name`, `prompt`) into the hidden
  `goals hooks user-prompt` can fake a reply. Replies show verbatim everywhere so
  the user can catch one; checking the host transcript was rejected as brittle.
- Codex: `goals setup --agent codex` wires the same hook into Codex's
  `hooks.json`; its payload field names (`prompt`, `cwd`, `session_id`) are
  assumed to match Claude Code's and aren't verified. If they differ the hook
  records nothing, and the agent closes with `--unverified` (labelled).
- A lock abandoned by a dead process is broken on POSIX; two processes breaking
  the same stale lock at once can still race (needs `flock`). Deferred.
- `goals validate` fails in both directions while two CLI versions write the
  same goal (strict `goal.json` load); `goals repair` fixes it.
- The plugin runs whatever `goals` is on PATH and never upgrades it, so a new
  skill can meet an old CLI (`No such command 'want'`). Hooks fail open. Deferred.
- Each prompt pays ~180ms to start the CLI for the hook, even in repos with no
  goal (goals that aren't waiting are skipped without a replay). Deferred (a
  lighter hook entry point).
- A nested, non-interactive session that reuses the host session id (e.g.
  `claude -p --resume "$CLAUDE_CODE_SESSION_ID" ...`) — or, on Codex, any subtask
  prompt — can be recorded as a reply. Replies show verbatim for the user to
  catch; one reply answers one question.
- On a single-phase goal, a property only the user can judge is checked in that
  same phase, so it can be asked during Discovery.
- *(Follow-up, plan re-audit 2026-09-26)* After a revision, a later phase's
  re-review runs the gate on its pre-revision evidence; it doesn't force a fresh
  `goals phase verify` against the new framing.
- *(Follow-up, plan re-audit 2026-09-26)* `goals phase review` prints "pass"
  directly above any "Not verified: …" line; the summary line itself doesn't say
  how many user answers weren't verified.
- Gate messages quote property text, which `goals memory absorb` can carry into
  self-evolution memory (pre-existing for assumption text too).

### Threat model

The agent runs every `goals` command and can write every file, including the
event log and the hook entry points, so nothing in-process can *prove* the user
said yes. The target is an **over-eager agent that shortcuts**, not a hostile
one: make the honest path the only easy path, make a shortcut take a deliberate
forgery, and show the user the exact words that counted as their yes so they can
catch one.

### Build order

Each step ships and meets its criteria before the next starts.

1. **Forward-compatible event log** — *implemented (PR #43); it must ship in a
   release before steps 2–5 write new event types.*
   - `EventStore.append` never rewrites existing lines; it appends. It used to
     rewrite the log from parsed events, so an older CLI permanently deleted
     event types and fields it didn't know.
   - New concepts get new event types, never new values in existing enums
     (`CheckpointKind`, `Assumption.status`) — an older CLI crashes on those.
   - `assess assume --phase` must name a phase that exists, as checkpoints
     already must.
2. **User-confirmation provenance.** — *implemented. As built: the event is
   `USER_MESSAGE_RECORDED` (the engine records the reply; the agent judges it,
   and every view shows the words); the rule covers every user checkpoint
   (`understanding`, `human_validation`, `approval`, or any put to the user), not
   only `understanding`; a question is stamped with the asking host session
   (`CLAUDE_CODE_SESSION_ID`) and only that session's replies count; one reply
   closes one question; `--unverified` is the labelled path for hosts without
   the hook; ownership is sticky, so no update (kind, status, `--optional`) can
   make a user checkpoint agent-closable.*
   - A Claude Code `UserPromptSubmit` hook records the user's own message
     verbatim as a `USER_CONFIRMATION` event while a `needs_user` `understanding`
     checkpoint is open.
   - The engine refuses `passed` or `waive` on an `understanding` checkpoint
     unless a `USER_CONFIRMATION` newer than its `needs_user` exists; the passing
     record cites it.
   - `goals check` and the dashboard show provenance: *"You said: '…'"* versus
     *"Recorded by the agent — not verified."*
   - Codex has no equivalent hook wired today, so it stays on the honest-agent
     path, labelled "not verified", until it does. *(As built: Codex 0.156 has
     stable hooks, so `goals setup --agent codex` wires the same one.)*
3. **Typed records.** — *implemented. As built: a `user` property's check is a
   real `human_validation` checkpoint event (same id) written before the
   property, so older CLIs still enforce it; it can't be asked before its phase
   is current; a property can't be bound to an accepted phase, and its phase and
   proof are fixed once recorded (change them by revising Discovery).*
   - `PainPoint` and `DesiredProperty` with stable ids (`PP-…`, `DP-…`) and
     their own event types, recorded with `goals assess pain` and
     `goals assess want`. Not a top-level `goals discover`: "discover" already
     means skill discovery, and `/goals:discover` runs the whole flow.
   - Each `DesiredProperty` carries `proof: auto | user` and a bound phase,
     validated to exist. `auto`: the bound phase's review needs an engine-run
     check whose `covers` is the `DP-` id — only `auto` counts, as for
     load-bearing assumptions. `user`: the last phase (`phases[-1]`) can't be
     accepted until a `USER_CONFIRMATION` for that property exists.
   - The skill switches from stand-ins to these commands in the same release;
     never dual-write. Goals already on stand-ins keep rendering as today — no
     history rewrite.
4. **Views and privacy.** — *implemented. As built: the plan said properties are
   "never logged to user memory" and also that recurring ones are promoted, which
   needs them logged; resolved (user-approved in the plan audit, 2026-09-26):
   Goals never writes pain or desired properties to memory, and the goal-end
   summary lists the user's wants with the `goals user record` command to keep
   any themselves. `decision record --private` keeps the whole decision off memory, not just
   its `--why`. A hand-written `DISCOVERY.md` is moved aside once, not
   overwritten.*
   - A dashboard "What you want / What hurts today" section, replacing
     properties-listed-as-assumptions.
   - `DISCOVERY.md` is generated from the events, like the dashboard, instead
     of hand-written.
   - Pain points and desired properties stay out of the `.goals/` export (it's
     an allowlist — keep them off it) and are never logged to user memory; the
     Discovery approach decision is logged without its `--why` text.
   - Memory promotion: only a desired property (never pain text) seen in two or
     more goals, offered through the existing confirm-before-promote digest.
5. **Re-framing mid-goal.** — *implemented as `goals assess revise --reason`. As
   built: it also resets the first phase's understanding checkpoints to pending
   (the user must say yes to the new framing, and an earlier reply no longer
   counts), waives the superseded properties' open user checks, clears reviews
   on every later phase — P2 included — and reopens a completed goal.*
   - A `DISCOVERY_REVISED` event supersedes the prior properties, clears P1's
     reviews (today `goals phase start P1` keeps a stale PASS), and flags
     later accepted phases for re-review in `goals check`.

### Decisions

- Desired properties are **not** acceptance criteria. Criteria are frozen when a
  goal starts and their ids are positional (`P3.C2`), and Discovery runs after
  the start; properties are a separate gate input with stable ids. *(Supersedes
  "link each desired property to the acceptance criteria that later prove it"
  and closes the open question on automatic mapping.)*
- A feel property is proven by the user's own words, not a `manual`
  verification — those are agent-authored.
- The user-only gate targets an over-eager agent (see Threat model). *(Supersedes
  the options "a confirm command only a person at the terminal can complete" —
  an agent can fake a TTY — and "`passed` must cite a `--by user` decision" —
  `--by user` is a self-declared label.)*
- *(Build, 2026-09-26)* Hosts without the reply hook close user checkpoints with
  `--unverified`, labelled "not verified" in every view, rather than being unable
  to finish. *(Resolves the plan's conflict between "the engine refuses" and
  "Codex stays on the honest path".)*
- *(Build)* Replies are bound to the asking host session when the host exports
  its id; otherwise the nearest checkout decides, and two waiting worktree goals
  make a base-checkout reply ambiguous, so it's recorded nowhere.
- *(Build; approved in the plan audit, 2026-09-26)* Desired properties are never
  written to memory; the goal-end summary offers each one as a `goals user
  record` command the user runs themselves. *(Replaces "promote recurring ones",
  which needed them logged; Discovery wants can be health-adjacent.)*
- *(Approved in the plan audit, 2026-09-26)* `--unverified` closes a user
  checkpoint only after it was put to the user, and every view — including
  `goals phase review`, `phase accept`, and `goals finish` — says it wasn't
  verified. *(Amends the P0 criterion below: the listed commands fail until a
  reply is recorded, unless the host can't record one.)*
- *(Approved in the plan audit, 2026-09-26)* Three review fixes outside the plan
  stay: breaking a lock left by a dead process (POSIX), `assess assume --id`
  keeping what it leaves out, and `phase accept` re-checking load-bearing
  assumptions as well as desired properties bound after the last review.

### Validation criteria

Ticked from automated tests unless marked; file names are under `tests/`.

P0 — block release:
- [x] (auto) An older CLI appending to a log that contains an unknown event
  type leaves that line byte-identical. *(test_storage.py)*
- [x] (auto) `checkpoint record P1 alignment --status passed` and
  `checkpoint waive P1 alignment` both fail while it is `needs_user` with no
  newer `USER_CONFIRMATION`, and both succeed after one. *(test_user_confirmation.py;
  the event is `USER_MESSAGE_RECORDED`; amendment approved: once asked, `--unverified`
  also closes it, labelled "not verified" everywhere)*
- [x] (auto) An `auto` property blocks its phase's review until an engine-run
  check covering its `DP-` id passes; a `manual` verification covering it
  doesn't count. *(test_discovery_records.py)*
- [x] (auto) A `user` property blocks accepting `phases[-1]` on a custom
  two-phase loop. *(test_discovery_records.py, via `goals phase accept`)*
- [x] (auto) After recording pain points and properties, none of their text
  appears in `.goals/goal-state.json`, `.goals/GOAL.md`, or
  `~/.goals/user/observations.md`. *(test_discovery_views.py, through goal
  completion)*

P1:
- [x] (auto) `assess assume --depends --phase P9` on a four-phase goal errors.
- [x] (auto) A stand-in goal replays and renders with no duplicate entries in
  the new view. *(test_discovery_views.py)*
- [x] (auto) `DISCOVERY_REVISED` clears P1's reviews and flags accepted later
  phases; `goals check` names what needs re-review. *(test_discovery_revision.py)*
- [x] (manual) A non-technical reader can tell from the dashboard alone what
  they said yes to and whether that yes was verified. *(checked in an end-to-end
  scratch run: "you said yes: …", "Your replies on record", "not verified"; a
  human read-through is still worth doing)*
- [x] (manual, Codex) The gate reads "not verified" rather than implying proof.
  *(automated for `--unverified`; not run inside Codex itself)*

P2:
- [x] (auto) `goals assess pain` and `goals assess want` exist; there is no
  top-level `goals discover`. *(test_discovery_views.py)*
- [x] (auto) The generated `DISCOVERY.md` matches the event log after each
  Discovery command. *(test_discovery_views.py, test_discovery_revision.py)*

Rollback signal: an event missing from `events.jsonl`, or a goal stuck in P1
with the user's yes in chat but no `USER_CONFIRMATION` — turn off the engine
refusal, keep the provenance labels, and investigate.

### Open Questions

- ~~Does the `UserPromptSubmit` payload carry the user's text reliably?~~
  Answered: yes — `prompt` is the raw typed text (slash commands arrive
  unexpanded; the hook skips them), it fires only for human prompts, and exit 0
  with no output leaves the prompt untouched. Several open questions: replies
  bind to the asking session; see Decisions.
- ~~What user-message hook does Codex expose?~~ Codex 0.156 has `UserPromptSubmit`
  in `hooks.json`; its payload fields are still unverified (see Known limitations).
- ~~Should a mid-goal revision also send P2 back?~~ Yes: every later phase loses
  its reviews, and accepted ones need review again.
- Should the plugin upgrade a stale `goals` CLI it finds on PATH?

### Critique cycle 1 (2026-09-26)

Frame (from an independent agent): consent provenance (P0), gate semantics for
properties (P0), event-schema evolution (P1), re-framing lifecycle (P1), privacy
of free text (P1), single source of truth (P2). Excluded: performance and scale
(small, local logs); cost and observability (no new services).

Evidence, read from code: `storage.py:181-189` (append rewrites the log from
parsed events), `criteria.py:14-24` (positional criterion ids), `runtime.py:196-223`
(criteria frozen at `GOAL_CREATED`), `hooks/hooks.json` (only `SessionStart` and
`Stop`), `cli.py:1529` (`--by` is self-declared), `cli.py:817-829` (waive has no
guard), `portability.py:97-110` (breakdowns exported verbatim),
`decision_workflows.py:92-117` (`--by user` writes global memory),
`runtime.py:369-373` (an orphan assumption phase matches no gate).

Criteria completeness: 7/10 — the hook payload and Codex parity are unverified.

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
