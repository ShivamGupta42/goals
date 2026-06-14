---
name: goals-decision-explainer
description: Explain a project decision from the active Goals goal in plain language — what needs the user, the recommended reply, and what happens next. Use inside a Goals project when a technical decision, risk, or tradeoff needs a non-technical explanation, or when deciding whether a choice should interrupt the user.
---

# Goals Decision Explainer

Ships with the Goals CLI. Works **inside a Goals project** (a goal worktree with
active state created by `goals start`).

## When to use
- A technical decision, migration, or high-risk tradeoff needs a plain-language
  explanation for a non-technical user.
- You need to know whether a choice should interrupt the user or can stay with
  the agent.

## How to run
1. Start with the compact brief (zero-arg, reads the active goal):
   ```bash
   goals decision brief
   ```
   It shows only choices that need the user, the recommended reply, what happens
   after, and how many routine choices can stay with the agent.
2. To explain one specific decision file at a chosen depth:
   ```bash
   goals decision explain --file decision.json --level basic   # or detailed, technical
   ```

If there is no active Goals goal, this skill does not apply — run it from a goal
worktree created by `goals start`.
