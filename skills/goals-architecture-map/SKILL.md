---
name: goals-architecture-map
description: Show the architecture map of the active Goals goal — what is built, planned, blocked, deferred, or missing. Use inside a Goals project when you need the system shape, a diagram-style overview, or to check recorded changes against the goal's architecture.
---

# Goals Architecture Map

Ships with the Goals CLI. Works **inside a Goals project** (a goal worktree with
active state created by `goals start`).

## When to use
- You need the shape of what is being built: phases, and what is done, planned,
  blocked, or deferred.
- You want to check whether recorded changes match the goal's architecture map.

## How to run
```bash
goals architecture show     # full map
goals architecture brief    # compact overview
goals architecture check    # compare recorded changes/evidence to the map
```

If there is no active Goals goal, this skill does not apply — run it from a goal
worktree created by `goals start`.
