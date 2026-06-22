# Contributing to Goals

Thanks for helping out. Issues and PRs are welcome, from a one-line typo fix to a
new loop adapter.

Goals is a small Python CLI plus a Claude Code / Codex plugin. It keeps a goal,
its decisions, and its evidence as plain files you own. The same discipline the
tool enforces on agents applies here: a change is done when its checks actually
run and pass.

By taking part, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a bug or rough edge.** Open an issue with what you ran, what you
  expected, and what happened. A failing `goals ...` command plus its output is
  the most useful thing you can include.
- **Suggest a feature.** Open an issue first so we can agree on the shape before
  you build it. Goals keeps a small public command surface on purpose.
- **Send a PR.** Fixes, tests, docs, and loop adapters are all fair game.
- **Improve a skill.** Bundled skills under `skills/` are executable agent
  guidance. If repeated friction changes how an agent should work, update or add
  a skill rather than hard-coding around it.

## Dev setup

You need [uv](https://astral.sh/uv) (it provisions Python 3.11+ for you):

```bash
git clone https://github.com/ShivamGupta42/goals.git
cd goals
uv sync                # install deps into a local .venv
uv run goals --help    # run the CLI from source
```

## Run the checks before you push

These mirror CI, so run them locally first:

```bash
uv run pytest -q                                   # tests
uv run ruff check .                                # lint
uv build --wheel --out-dir /tmp/goals-wheel        # build the wheel
uv run python scripts/check_bundled_skill_wheel.py /tmp/goals-wheel/*.whl   # bundled-skill inventory matches source
uv run goals validate                              # validate goal state + registries
```

For a focused change, run the tests for the area you touched, then the full
`uv run pytest -q` when the change affects shared behavior. If you edit a skill,
a command's docs, or any `goals ...` example, run the skill-hygiene tests so
stale references and malformed frontmatter are caught before merge:

```bash
uv run pytest -q tests/test_skill_hygiene.py
```

## Conventions

- **Reuse before adding.** Prefer existing modules and tests over new subsystems.
  Reuse `goals start`, `goals next`, `goals check`, `goals view`,
  `goals loop improve`, and `goals skills` before adding a new command.
- **Add tests for new paths**, including the edge cases. Goals gates "done" on
  executed proof; contributions follow the same bar.
- **Keep skill folders lean:** `SKILL.md` plus optional `scripts/`,
  `references/`, and `assets/`. Put contributor guidance in `skills/README.md`,
  not inside each skill folder.
- **Don't touch managed-context blocks.** Preserve human-authored content outside
  the `<!-- goals:context:start -->` / `<!-- goals:context:end -->` markers.
- **Match the surrounding style.** Keep the diff surgical: every changed line
  should trace to the change you're making.

See [`AGENTS.md`](AGENTS.md) for the same guidance aimed at AI agents working in
the repo, and the **For developers** section of the [README](README.md) for how
the pieces fit together.

## Pull request process

1. Branch off `main` (e.g. `git checkout -b fix-loop-import-path`).
2. Make the change and add or update tests.
3. Run the checks above. Green tests and clean `ruff` are the bar.
4. Open the PR with a short description: what changed and why. Link the issue it
   closes if there is one.
5. Keep PRs small and focused. Unrelated changes are easier to review as separate
   PRs.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
