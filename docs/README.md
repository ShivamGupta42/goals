# Goals Docs

Start with the root `README.md` for user-facing setup and workflow commands.
This directory holds deeper design notes and long-lived project context.

## Guides

- `SELF_EVOLUTION.md` - how Goals records friction, derives suggestions, and
  keeps private memory separate from committable project state.
- `skill-evolution/README.md` - when repeated workflow friction should become a
  skill update.
- `DOGFOOD_FINDINGS.md` - observations from using Goals on itself.
- `WORKFLOW_IMPROVEMENTS.md` - improvement list from real-world goal loop
  simulations.
- `LOOP_IMPORT.md` - importing external loops/catalogs and validating them with
  profile-backed proof requirements.
- `goals-repo-guide.html` - generated visual guide to the repository.

## Maintenance

- Keep command examples aligned with the Typer CLI. Stale `goals ...` examples
  should fail `tests/test_skill_hygiene.py`.
- Keep docs honest about setup: `goals setup` installs agent integration pieces,
  while `goals context sync` writes managed context blocks into `AGENTS.md` and
  `CLAUDE.md`.
- Prefer updating these docs over adding new top-level taxonomies unless the new
  structure becomes a real interface.
