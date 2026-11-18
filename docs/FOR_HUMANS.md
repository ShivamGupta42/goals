# Goals — for the person in charge

A one-page cheatsheet. You describe what you want; the AI agent does the work;
Goals keeps it on track. This page tells you what to expect and what to do when
the AI asks you something.

## What you'll see the AI do

| The AI says … | What that means | What you need to do |
|---|---|---|
| `goals start "build me a log-in page"` | The AI is creating a tracked 4-phase plan. It'll print a dashboard link. | Confirm the objective. That's it. |
| "Here's what I understand — is this what you want to build?" | Phase 1 (Discovery). The AI is checking it understood you correctly before writing any code. | Read the summary. Say yes, or correct it. A "no" now saves the most time. |
| `goals check` → "Waiting on: you" | Something needs your decision before the AI can continue. | Read the question in the output. Give a plain-language answer. |
| `goals phase accept P3` | The AI ran its checks and they passed. It wants to mark this phase done. | Briefly check the evidence. If it looks right, say yes. |
| `goals finish` | All phases are accepted. The AI is running the final closeout checks. | Review the summary. Merge or deploy if you're ready. |

## The 4 default phases

Every goal runs through these phases. The AI moves through them one at a time:

```
P1 — Confirm outcome    →   AI asks: "Is this what you want?"
P2 — Inspect project    →   AI looks at the codebase to plan
P3 — Execute            →   AI builds the thing
P4 — Review & close     →   AI verifies, records decisions, wraps up
```

P1 is the most important. If the AI misunderstood you there, everything after
it is wrong. Read the summary, correct it freely — a fix here costs minutes, not
hours.

## What "done" really means

The AI doesn't say "done" because it *feels* done. It says "done" because:

1. It declared specific checks (e.g. `pytest tests/`, `npm run build`)
2. The **engine** actually ran those checks (`goals phase verify`)
3. The checks passed with real exit codes (not the AI's claim)
4. A gate review confirmed no gaps remain

If you see "Evidence: 4 checks, confidence 0.8" in a dashboard — the checks are
real and machine-verified. The confidence number is the AI's subjective
assessment; the checks are objective.

## Three signs something needs your attention

| Sign | What's happening | What to do |
|---|---|---|
| **"Waiting on: you"** | The AI hit a decision it can't make alone — usually safety, cost, or a design choice. | Read the question. Answer in plain English. |
| **Same phase retried 3 times** | The AI keeps failing the gate review. `GOALS_MAX_PHASE_ATTEMPTS` caps it at 3 by default. | Check whether the goal is too hard or the AI is going in circles. Simplify or reset. |
| **AI never asks you anything** | Running at `standard` autonomy. Fine for straightforward goals. | If the goal is important or risky, restart with `--autonomy careful` to get more checkpoints. |

## Commands you can run yourself

| You type | What happens |
|---|---|
| `goals check` | Plain-language status: progress, proof, what needs you |
| `goals view --open` | Open the dashboard in your browser |
| `goals user show` | See what Goals has learned about your preferences |
| `goals next` | See what the AI should do next (the next handoff prompt) |
| `goals finish` | Run closeout checks on a completed goal |

## What is Goals, really?

Think of it as a **project manager for your AI agent**:

- The AI does the actual work (writes code, runs tests, commits)
- Goals keeps the **plan**, the **decisions**, and the **proof** in plain files
- When you `/clear` or start a new session, the goal survives — it's on disk, not
  in the AI's memory
- You own every file. Nothing is in a database or a server

Everything is in your repo under `.agent-workflow/` (runtime state) and
`.goals/` (portable export safe to commit). You can read, edit, or delete
anything by hand.

## See also

- [`README.md`](../README.md) — full setup and command reference
- [`architecture.md`](architecture.md) — system architecture and lifecycle diagrams
- [`subsystems.md`](subsystems.md) — memory, decision rules, stop gates
- [`GOAL_EXECUTION_MEMORY.md`](GOAL_EXECUTION_MEMORY.md) — how Goals learns your preferences