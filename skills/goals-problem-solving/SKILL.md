---
name: goals-problem-solving
description: Solve a problem or define/break down a goal using PACERS (Pause, Assess, Choose, Execute, Review, Systemize) and record the reasoning as a traceable building journey in the active Goals goal. Use inside a Goals project when defining a goal, breaking a phase into sub-problems, hunting assumptions before building, or whenever a problem is recurring, costly, unclear, or likely to create second-order effects.
---

# Goals Problem Solving — PACERS

Ships with the Goals CLI. Works **inside a Goals project** (a goal worktree with
active state created by `goals start`). It turns the model's reasoning into a
plain-English trace the user can read on the dashboard — the *building journey*.

PACERS is a six-step loop that forces a second look before the first acceptable
answer becomes the final answer. Not every problem needs the full loop — use it
when a problem is **recurring, costly, unclear, or likely to create second-order
effects**. A one-line typo fix does not need PACERS.

## The loop

**1. Pause — become aware before acting.**
Ask one sharper question before the first move: *am I solving the problem, or just
reducing my own discomfort / accepting my first answer?* Watch for the eager state
(action feels urgent) and the distracted state (attention too fragmented to hold
the whole problem). If you're soothing discomfort, slow down. Record the check as
the breakdown's `pause_note`.

**2. Assess — make the problem clear.** This is the heart of the journey.
- **Rephrase** the vague statement into a specific, testable one.
- **Ask why until it simplifies** (5 Whys) — record the chain in `whys`.
- **Hunt assumptions.** Write down what you're assuming. You don't need to
  eliminate every assumption — you need to know **which ones your solution
  depends on**. Record each with:
  ```bash
  goals assess assume "I'm assuming X" --building "the thing I'm building" \
    --toward "the sub-problem it serves" --depends --status holding \
    --phase <PHASE> --college "extra framing for a college reader" \
    --hobbyist "how a tinkerer would poke at it"
  ```
  Write the bare `statement` at a **high-school reading level** — no jargon. It is
  the always-visible text; `--college` / `--hobbyist` only *add* framing.
- **Look at the system** for recurring problems: what keeps feeding this? Record as
  `system_view`.
- Record the whole breakdown (problem → sub-problems → tasks → open questions):
  ```bash
  goals assess breakdown --file breakdown.json
  ```

**3. Choose — compare solutions before committing.**
Generate at least a few options (obvious, simplest, systemic, and the no-action
option). Make tradeoffs visible: effectiveness, time, effort, risk, **reversibility**,
cost, second-order effects. Prefer a slower reversible action over a fast
destructive one. Record the call with `goals decision record` (or surface it with
`goals decision brief` / `goals decision explain` when it needs the user).

**4. Execute — run the chosen plan, and prove it by execution.**
A good plan has a first step, a **stopping rule**, a way to verify progress, and a
rollback if risky. Build only the chosen thing. Then prove it ran, don't narrate
that it works. First **invert** (this is where hidden bugs live): deliberately try
to break what you built — how could it fail across boundaries and signs, time and
locale, empty and huge inputs, concurrency, and its dependencies (storage, network,
the clock) failing? The gate only makes you defend the assumptions you *name*, so
for each plausible failure either fix it, write a check that exercises it, or — if
it's a premise you were silently relying on — record it as a load-bearing
assumption. Then, for each acceptance criterion **and** each load-bearing
assumption, write a runnable check that **fails if it's wrong** (a check that can't
fail proves nothing). Record them in the evidence `verifications` (each `covers` a
criterion or an assumption id) with `goals phase evidence`, then
`goals phase verify` — the engine runs your checks and records the real exit codes,
so a passing result can't be asserted, only earned. Fix until every automated check
passes, then `goals phase review` and `goals phase accept`.

**5. Review — learn from the result.**
Did this solve the *actual* problem? What did you expect vs. what happened? Which
step was weak? If an assumption turned out false, flip it:
```bash
goals assess assume "..." --id <A-id> --status broken
```

**6. Systemize — prevent repeat problems.** Only for recurring or costly problems.
Turn the lesson into an environment change (a checklist, a decision rule, a
template) via `goals improve`. Don't build a system before you understand the
problem.

## When NOT to use
Trivial, one-off, reversible work. Clean up the spilled coffee — don't run the loop.

If there is no active Goals goal, this skill does not apply — run it from a goal
worktree created by `goals start`.
