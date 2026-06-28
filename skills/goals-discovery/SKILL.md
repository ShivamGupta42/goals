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
anything yet.

**2. Draw out the desired feel and properties.**
Turn the pain into the properties of a good outcome. Ask how they'll know it
worked, what "good" feels like, what would make them *not* trust or use it. You're
collecting things like *"fast enough that I never wait,"* *"I can hand it to my
mum,"* *"I trust the number without checking it,"* — not screens and buttons.
Record each as a property the solution must have, in their words where you can:

```bash
goals assess assume "The result has to feel <property> — <what that means here>" \
  --building "the thing we're making" --toward "the user's real outcome" \
  --status holding
```

Write them at a high-school reading level — no jargon. These are the success
targets the build should later honour. Record them as **plain** assumptions here —
do **not** add `--depends` at phase one. A `--depends` (load-bearing) assumption
attaches to the current phase (Confirm) and makes the gate demand a runnable check
that would *fail if it's wrong* before that phase can pass — but a "feel" property
like *"instant to log"* can't be tested until there's something built. Capture the
property now; the place to prove it is the phase that builds it. (Enforcing that
link automatically is the "first-class durable discovery" item on the roadmap.)

**3. Name what you do NOT understand — out loud.**
This is the heart of Discovery. Instead of quietly assuming, list the gaps: the
ambiguous words, the unstated scope, the "it depends" forks, the things only the
user can settle. Each unknown is an open question, not a guess to paper over.
Record them so they travel with the goal — each unknown as its own line:

```bash
goals assess breakdown --problem "<the user's goal, rephrased plainly>" \
  --subproblem "Open question: <something you genuinely don't yet understand>"
```

(For the fully structured form — sub-problems each carrying their own
`open_questions` — author the breakdown as JSON with
`goals assess breakdown --file breakdown.json`; see `goals-problem-solving`.)

Prefer one honest "I don't know X yet" over ten confident assumptions. If you
*must* lean on an assumption to move, record it with `goals assess assume` so it
stays visible and can be revisited. Mark it `--depends` only once you can write a
check that fails if it's wrong, and `--phase` it to the phase that runs that check
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
in the same breath. Record the call so the reasoning is on the dashboard:

```bash
goals decision record "How we'll approach <goal>" --choice "<the path>" \
  --why "<plain reason it best fits their pain + desired feel>"
```

Use `goals decision brief` if the choice genuinely needs the user to pick.

**6. Get an explicit yes — the alignment gate.**
Don't slide into building. Ask plainly: *"Here's what I understand and how I'd
approach it — is this what you want to build?"* Record it as a checkpoint that
**needs the user** and **blocks** the rest of the run until they confirm:

```bash
goals checkpoint record P1 alignment --kind understanding --status needs_user \
  --needs-user --title "Does this match what you want to build?" \
  --summary "<one-line of the understanding + approach awaiting their yes>"
```

When the user confirms, flip it and proceed to Assess:

```bash
goals checkpoint record P1 alignment --kind understanding --status passed \
  --summary "User confirmed: <what they agreed to>"
```

If they correct you, fold the correction back in (steps 2–5) and re-ask. A "no"
here is the cheapest, most valuable feedback in the whole run.

## Write `DISCOVERY.md`

Leave a plain-file record in the goal worktree — yours to read and edit — with
five short sections:

- **What hurts today** — the pain points and friction, in the user's words.
- **What good feels like** — the desired properties of the outcome (not features).
- **What I don't understand yet** — the open questions, honestly listed.
- **How I'd approach it** — the options with plain-English pros and cons.
- **What the user confirmed** — exactly what they said yes to (and any "no"s that
  reshaped the plan).

## Quality bar

- Lead with **pain and feel**, not features. If your notes are a feature list,
  you skipped the user.
- Make every unknown **explicit**. An unsurfaced assumption is the bug.
- Plain English throughout — a non-technical user must be able to weigh the
  pros and cons and answer the alignment question without decoding jargon.
- Do not start building until the alignment checkpoint is `passed`.

## When NOT to use
A trivial, unambiguous, reversible task with no real person-context to understand.
Fix the typo; don't run Discovery. And if there is no active Goals goal, this
skill does not apply — run it from a goal worktree created by `goals start`.
