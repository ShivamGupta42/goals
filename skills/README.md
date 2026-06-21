# Goals Skills

This directory contains Goals' bundled skills. They are packaged into the wheel
as `goals/bundled_skills` and can be copied into Claude or Codex skill dirs with
`goals skills install`.

## When To Add Or Update A Skill

Use a skill when a lesson should change future agent behavior, not merely record
what happened once.

- Add or update a skill after repeated friction, a high-severity mistake, or a
  cross-project lesson that changes how agents should work.
- Keep one-off observations in self-evolution memory or docs until they repeat.
- Prefer updating an existing skill when the behavior belongs to an existing
  workflow.
- Add a new skill only when it has a distinct trigger, workflow, or reusable
  resource set.

## Skill Shape

- Each skill lives in a folder whose name exactly matches frontmatter `name`.
- Each skill must have `SKILL.md` with YAML frontmatter containing only `name`
  and `description`.
- Write `description` as the trigger: what the skill does and when an agent
  should use it.
- Keep `SKILL.md` concise. Use optional `scripts/`, `references/`, and `assets/`
  when deterministic code, detailed reference material, or output resources are
  needed.
- Do not add README, install guide, changelog, or other auxiliary docs inside an
  individual skill folder.

## Validation

- Run `uv run pytest tests/test_skill_hygiene.py tests/test_skill_discovery.py -q`
  after changing bundled skills.
- Command references such as `goals loop improve` must resolve to real CLI
  commands.
- Release checks must confirm every source skill appears in the built wheel.
