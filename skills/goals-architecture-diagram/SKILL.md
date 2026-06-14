---
name: goals-architecture-diagram
description: Generate a clean architecture or loop diagram for the active Goals goal as Mermaid or a valid .excalidraw file. Use when the user asks to visualize, diagram, or draw the goal's architecture map or the designed loop.
---

# Goals Architecture Diagram

Render the active Goals goal's architecture map (or a designed loop) as a clean
diagram. Generation is deterministic — it comes from goals' own structured model,
not freehand analysis — so the output is consistent and correct.

## Use

```bash
# Mermaid (default) — renders in GitHub / markdown / the dashboard
goals diagram --source architecture
goals diagram --source loop

# Excalidraw — a valid .excalidraw file you can open at excalidraw.com or in the
# VS Code Excalidraw extension
goals diagram --source architecture --format excalidraw --out goal.excalidraw
```

`--source architecture` uses the active goal's architecture map; `--source loop`
uses `.goals/loop-design.json` from the visual loop builder. Requires an active
Goals goal (run from its worktree, or an in-place goal's repo).

## Notes

- Nodes are colored by status (built / in-progress / planned / blocked /
  deferred).
- The Excalidraw output follows raw-JSON rules so it renders correctly:
  rectangles (not diamonds), each label as a bound text element, elbow arrows
  that attach at shape edges.
