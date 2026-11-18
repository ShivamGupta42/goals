# Codex Agents

Goals is a Python CLI for durable, evidence-backed agent workflows. Keep this
file shareable: no secrets, local absolute paths, hostnames, or personal config.

## Known constraints (surprising, enforced by code)

These fail at runtime if you don't know them. Learn them once, and you won't hit them again.

- **`extra="forbid"` on all data models** — the Evidence, Verification, Event, and
  every other model reject unknown keys. Do not add fields like `summary` on
  Evidence; use the existing `notes` field. A pydantic error with a readable
  message will name the offending key and list the allowed fields.
- **Engine owns `ran`/`passed` on verifications.** You can set them in your
  evidence JSON, but `goals phase verify` overwrites them with the real exit
  codes. Declare the verifications you want; the engine proves them. The notice
  "ignored agent-set results on N verification(s)" means this happened.
- **Load-bearing assumptions need a falsifier.** An assumption recorded with
  `--depends` must have an `auto` verification whose `covers` is the assumption
  id, bound to the same phase. The gate rejects a load-bearing assumption with
  no automated check that could prove it wrong.
- **Phase P1 (Confirm) alignment checkpoint needs a real user reply.** Only the
  Goals hook's recorded message can close it. On a host without the hook, use
  `--unverified` — the checkpoint closes but is labelled "not verified"
  everywhere.
- **Gate review is verified evidence only.** A phase passes review only when
  each acceptance criterion and each load-bearing assumption has a verification
  the engine actually ran and that passed. Narrated proof ("I tested it and it
  works") is not enough.
- **One goal per directory without a worktree.** You cannot create a second
  in-place goal in the same repo root. Use `--worktree` (or `git checkout -b`
  first) to run parallel goals.

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
