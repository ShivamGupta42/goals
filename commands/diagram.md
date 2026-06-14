---
description: Render a clean diagram of the goal's architecture or loop.
argument-hint: [architecture|loop]
---

Generate a diagram for the active goal.

Run `goals diagram --source ${ARGUMENTS:-architecture} --format mermaid` and show
the user the Mermaid output (it renders in the dashboard and GitHub). If they
want an editable file, run
`goals diagram --source ${ARGUMENTS:-architecture} --format excalidraw --out goal.excalidraw`
and tell them it opens at excalidraw.com or in the VS Code Excalidraw extension.
