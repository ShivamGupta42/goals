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
Record each as a property the solution must have, at a high-school reading
level — no jargon — and **without private details** (health, family, money,
names): property statements and open questions are copied into the goal's
`.goals/` spec, which is meant to be committed with the project. Keep the user's
own words in `DISCOVERY.md` and checkpoint summaries, which stay local. These are
the success targets, so record each one where the run will actually be held to
it. Sort each property into one of two kinds:

- **Measurable** — a check could fail if it's wrong (*"logging takes under 5
  seconds,"* *"works with no internet"*). Record it as load-bearing on the phase
  that builds it — P3 (Execute) in the default Confirm → Inspect → Execute →
  Review arc:

  ```bash
  goals assess assume "The result has to <property> — <what that means here>" \
    --building "the thing we're making" --toward "the user's real outcome" \
    --depends --phase P3
  ```

  P3's review then won't pass without an automated check, run by
  `goals phase verify`, whose `covers` is this assumption's id.

- **A feel only the user can judge** (*"I can hand it to my mum,"* *"I trust the
  number without checking it"*). No automated check can prove it — it's the
  user's call once there's something to try. Record it as a user check on the
  last phase — P4 (Review) in the default arc — left `pending` for now:

  ```bash
  goals checkpoint record P4 feel-<short-name> --kind human_validation \
    --status pending --title "Ask the user: does it feel <property>?" \
    --summary "Their words: <how they described it>"
  ```

  P4 can't be accepted while it's pending. Don't waive it, and don't set it to
  `needs_user` before P4 — that puts the question to the user now, before there's
  anything to judge. In P4, set it to `needs_user` and ask; when they answer, set
  it to `passed` with their words.

Never tag a property `--depends` on P1 (Confirm): the gate would demand an
automated check before Confirm can pass, and there's nothing built to check yet.
If the goal runs a custom loop, use its build phase and its last phase instead
(the dashboard lists them; an unknown phase id is rejected).

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
after the second `|` shows on the dashboard as an open question.)

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
goals decision record "How we'll approach <goal>" --choice "<the path>" --by agent \
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
  --by user --why "<their reason, minus private details>"
```

A `--by user` decision is also copied into the user's memory across all their
projects, so keep private details out of its `--why`.

If they correct you, fold the correction back in (steps 2–5) and re-ask. A "no"
here is the cheapest, most valuable feedback in the whole run.

Don't run `goals phase review P1` while this checkpoint is waiting: all it can
return is "needs you", and each review counts toward the phase's attempt cap.
Record P1's evidence and review after the yes.

## Write `DISCOVERY.md`

Leave a plain-file record next to the goal's dashboard, at
`.agent-workflow/goals/<goal>/DISCOVERY.md` (the folder `goals check` prints as
*Dashboard*) — yours to read and edit. That folder stays out of git, so the notes
never land in the project's commits, and each goal keeps its own. Five short
sections:

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
- Put every desired property where the run is **held to it** — a P3 load-bearing
  assumption or a P4 user check. A property recorded nowhere enforceable is a wish.
- Keep private details out of anything recorded with `goals assess` or
  `goals decision record --by user` — those leave this goal. `DISCOVERY.md` and
  checkpoint summaries stay local.
- Plain English throughout — a non-technical user must be able to weigh the
  pros and cons and answer the alignment question without decoding jargon.
- Do not start building until the alignment checkpoint is `passed`.

## When NOT to use
A trivial, unambiguous, reversible task with no real person-context to understand.
Fix the typo; don't run Discovery. And if there is no active Goals goal, this
skill does not apply — run it from a goal worktree created by `goals start`.
