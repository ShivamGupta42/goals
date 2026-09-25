---
name: goals-discovery
description: Phase one of a goal — understand what the user actually wants before any building starts. Begin from their pain points and friction, draw out the *properties and feel* of a good outcome (not a feature list), name out loud what you do NOT yet understand instead of assuming it, lay out the approach with plain-English pros and cons a non-technical person can weigh, and get an explicit "yes, this is it" before Assess and build. Use right after `goals start`, before `goals-problem-solving`, on any goal that is not trivial and unambiguous.
---

# Goals Discovery — understand before you build

Ships with the Goals CLI. Run it **first**, right after `goals start` and
**before** Assess (`goals-problem-solving`). It is the step that keeps the rest
of the run aligned: most wasted work comes from building a clear answer to the
wrong question.

The default failure mode is jumping straight to *solving*. The agent hears a
goal, fills the gaps with its own assumptions, and ships something coherent that
was never quite what the user meant. Discovery exists to stop that: slow down,
understand the **person and their pain**, and only then frame the problem.

A trivial, unambiguous goal does not need this — a typo fix or a one-line tweak
goes straight to work. Use Discovery when the goal is open-ended, when the user
isn't technical, or when "what they asked for" and "what they want" might differ.

## The principle

> Users often can't tell you *what* to build. What they reliably know is **how it
> should feel** and **what hurts today**. Start there.

So don't mine the goal for features. Mine it for **pain points** (what's hard or
annoying now) and **desired properties** (how the finished thing should feel and
behave). Features are guesses about *how*; properties and pain are the *what* and
*why*, and they're what the user can actually confirm.

## The flow

**1. Start from the pain, not the ask.**
Open with their world, not the solution. What's painful or annoying today? When
does it bite, and how often? What do they do instead right now, and why does that
fall short? Listen for the friction underneath the request — the goal is usually
a proposed *fix*, and the pain behind it is the real target. Don't propose
anything yet. Record each pain point, in plain words:

```bash
goals assess pain "<what's hard or annoying today, and when it bites>"
```

**2. Draw out the desired feel and properties.**
Turn the pain into the properties of a good outcome. Ask how they'll know it
worked, what "good" feels like, what would make them *not* trust or use it. You're
collecting things like *"fast enough that I never wait,"* *"I can hand it to my
mum,"* *"I trust the number without checking it,"* — not screens and buttons.
Record each as a desired property, at a high-school reading level — no jargon.
These are the success targets, so each one says how the run will be held to it:

- **Measurable** — a check could fail if it's wrong (*"logging takes under 5
  seconds,"* *"works with no internet"*). Bind it to the phase that builds it —
  P3 (Execute) in the default Confirm → Inspect → Execute → Review arc:

  ```bash
  goals assess want "<property> — <what that means here>" --proof auto --phase P3
  ```

  P3's review then won't pass without an automated check, run by
  `goals phase verify`, whose `covers` is the property's id (`DP-…`).

- **A feel only the user can judge** (*"I can hand it to my mum,"* *"I trust the
  number without checking it"*). No automated check can prove it — it's the
  user's call once there's something to try:

  ```bash
  goals assess want "<property>" --proof user
  ```

  This adds a user checkpoint with the property's id to the last phase (P4,
  Review, in the default arc). That phase can't be accepted until it's closed on
  the user's reply (`--unverified` also closes it, shown as not verified). It
  can't be asked before its phase — there's nothing to judge yet — so when that
  phase is current, set it to `--status needs_user`, ask, and close it with
  `--status passed` once they answer. To change a property after the user has
  answered it, record a new one and ask them.

Never bind a property to P1 (Confirm): there's nothing built to check yet. If the
goal runs a custom loop, use its build phase for `--proof auto` (the dashboard
lists the phases; an unknown phase id is rejected) — `--proof user` finds the
last phase on its own.

Pain points stay on this goal: they're never exported to the goal's `.goals/`
spec or copied into the user's memory, so record them in the user's own words.
Desired properties aren't exported either, but once the user confirms Discovery
they're kept in the user's memory (so one that keeps coming back can become a
standing preference, with their say-so) — word them without private details.

**3. Name what you do NOT understand — out loud.**
This is the heart of Discovery. Instead of quietly assuming, list the gaps: the
ambiguous words, the unstated scope, the "it depends" forks, the things only the
user can settle. Each unknown is an open question, not a guess to paper over.
Record them so they travel with the goal — each unknown as an open question
under the part of the goal it's about:

```bash
goals assess breakdown --problem "<the user's goal, rephrased plainly>" \
  --subproblem "<the part it's about> | | <open question>; <another open question>"
```

(The empty middle slot is for tasks — there are none yet at phase one. Everything
after the second `|` shows on the dashboard as an open question.) Breakdowns are
copied into the goal's committable `.goals/` spec, so keep private details (health,
family, money, names) out of them.

Prefer one honest "I don't know X yet" over ten confident assumptions. If you
*must* lean on an assumption to move, record it with `goals assess assume` so it
stays visible and can be revisited. Mark it `--depends` only once you can write an
automated check that fails if it's wrong, and `--phase` it to the phase that runs that check
— the gate holds you to proving a load-bearing assumption *in its phase*, so an
untestable one tagged `--depends` here just blocks Confirm.

**4. Reflect their goal back in plain English.**
Before proposing anything, say what you now believe they're really trying to do
and *why* — pain → desired feel → the properties that matter. Keep it jargon-free
and short enough to read aloud. This is the mirror that lets the user catch a
misread before it becomes code.

**5. Lay out the approach with honest pros and cons.**
Now, and only now, sketch how you'd build it — and make it weighable by someone
non-technical. Give at least a couple of paths **including doing nothing / the
simplest thing**, each with plain pros and cons: what they gain, what it costs,
what's easy vs hard to undo later. No jargon; if a term is unavoidable, define it
in the same breath. Record your recommendation so the reasoning is on the
dashboard:

```bash
goals decision record "How we'll approach <goal>" --choice "<the path>" --by agent --phase P1 \
  --why "<plain reason it best fits their pain + desired feel>"
```

Keep `--by agent`: this is your recommendation, not yet their decision. The CLI
defaults to `--by user`, which would log a choice the user never made.

**6. Get an explicit yes — the alignment gate.**
Don't slide into building. Ask plainly: *"Here's what I understand and how I'd
approach it — is this what you want to build?"* Record it as a checkpoint that
**needs the user** and **blocks** the rest of the run until they confirm:

```bash
goals checkpoint record P1 alignment --kind understanding --status needs_user \
  --needs-user --title "Does this match what you want to build?" \
  --summary "<one-line of the understanding + approach awaiting their yes>"
```

When the user confirms, flip it, log the approach as *their* decision, and
proceed to Assess:

```bash
goals checkpoint record P1 alignment --kind understanding --status passed \
  --summary "User confirmed: <what they agreed to>"
goals decision record "How we'll approach <goal>" --choice "<the path they confirmed>" \
  --by user --phase P1 --private --why "<their reason, in their words>"
```

A `--by user` decision is also copied into the user's memory across all their
projects; `--private` keeps its `--why` on this goal only.

Only the user's reply can close this checkpoint. The Goals hook records what they
type while a checkpoint waits on them, and `--status passed` cites that reply —
it's refused if they haven't answered since you asked. On a host without the
hook, add `--unverified`: it closes, and every view says it wasn't verified.

If they correct you, fold the correction back in (steps 2–5) and re-ask. A "no"
here is the cheapest, most valuable feedback in the whole run.

If their understanding shifts **later** — mid-build, after they've said yes —
don't patch around it. Start Discovery over:

```bash
goals assess revise --reason "<what changed, in plain words>"
```

That sets aside what Discovery recorded, reopens P1 for a fresh yes, and sends
any phase already accepted back for review against the new framing. Then redo
steps 1–6 with them.

Don't run `goals phase review P1` while this checkpoint is waiting: all it can
return is "needs you", and each review counts toward the phase's attempt cap.
Record P1's evidence and review after the yes.

## `DISCOVERY.md`

Goals writes it for you, next to the goal's dashboard at
`.agent-workflow/goals/<goal>/DISCOVERY.md` (the folder `goals check` prints as
*Dashboard*), and rewrites it whenever the goal changes: what hurts today, what
good feels like (and where each property's proof stands), what's not understood
yet, how you'll approach it (the `--phase P1` decisions), and what the user
confirmed, in their words. That folder stays out of git, so it never lands in the
project's commits. Don't edit it by hand — record through the commands above.

## Quality bar

- Lead with **pain and feel**, not features. If your notes are a feature list,
  you skipped the user.
- Make every unknown **explicit**. An unsurfaced assumption is the bug.
- Record every desired property with `goals assess want` and an honest `--proof`
  — an automated check where one can fail, the user's judgement where only they
  can tell. A property recorded nowhere enforceable is a wish.
- Keep private details out of open questions (`goals assess breakdown`, exported
  to `.goals/`) and desired properties (kept in the user's memory once confirmed).
  Pain points, `DISCOVERY.md`, checkpoint summaries, and a `--private` decision's
  `--why` stay on this goal.
- Plain English throughout — a non-technical user must be able to weigh the
  pros and cons and answer the alignment question without decoding jargon.
- Do not start building until the alignment checkpoint is `passed`.

## When NOT to use
A trivial, unambiguous, reversible task with no real person-context to understand.
Fix the typo; don't run Discovery. And if there is no active Goals goal, this
skill does not apply — run it from a goal worktree created by `goals start`.
