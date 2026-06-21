# Codex Agents

Goals is a Python CLI for durable, evidence-backed agent workflows. Keep this
file shareable: no secrets, local absolute paths, hostnames, or personal config.

## Working In This Repo

- Prefer existing modules and tests over new subsystems. The stable state layer
  is the CLI plus `.goals/` portable exports; `.agent-workflow/` is local runtime
  state and is not a public contract.
- Keep public command surface small. Reuse `goals start`, `goals next`,
  `goals check`, `goals view`, `goals loop improve`, and `goals skills` before
  adding commands.
- Treat bundled skills as executable agent guidance. When repeated friction
  changes how an agent should work, update or add a skill and validate it.
- Keep individual skill folders lean: `SKILL.md` plus optional `scripts/`,
  `references/`, and `assets/`. Put contributor guidance in `skills/README.md`,
  not inside each skill folder.
- Preserve human-authored content outside Goals managed context markers:
  `<!-- goals:context:start -->` and `<!-- goals:context:end -->`.

## Verification

- Run focused tests for the area you changed, then `uv run pytest -q` when the
  change affects shared behavior.
- For skill or command documentation edits, run the skill hygiene tests so stale
  `goals ...` references and malformed skill frontmatter are caught before merge.
- For release work, build a wheel and compare bundled skill inventory against
  source `skills/*` before publishing.
