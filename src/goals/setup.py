"""One-command agent setup: wire goals into Claude Code and/or Codex.

`goals setup --agent claude|codex|both` actually performs the install
(idempotent; ``--dry-run`` previews). It is collision-safe: it merges into an
existing settings file without clobbering unrelated keys, and reuses the
collision-safe bundled-skill installer.

- **claude**: register this repo as a plugin marketplace and enable the `goals`
  plugin in ``~/.claude/settings.json``, plus install bundled skills.
- **codex**: install bundled skills into ``~/.agents/skills``. (Per-project
  goal context for Codex is synced into ``AGENTS.md`` by ``goals context sync``.)
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from goals.skill_discovery import CODEX_SKILLS_DIR, install_bundled_skills
from goals.storage import GoalsError, atomic_write_text

MARKETPLACE_REPO = "ShivamGupta42/goals"
MARKETPLACE_NAME = "goals"
PLUGIN_REF = "goals@goals"

_MARKETPLACE_SOURCE = {"source": {"source": "github", "repo": MARKETPLACE_REPO}}


class SetupAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    detail: str
    changed: bool


class SetupReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool
    actions: list[SetupAction] = Field(default_factory=list)


def setup_agents(
    targets: list[str],
    *,
    dry_run: bool = False,
    claude_home: Path | None = None,
    codex_home: Path | None = None,
) -> SetupReport:
    claude_home = claude_home or (Path.home() / ".claude")
    codex_home = codex_home or CODEX_SKILLS_DIR.parent
    actions: list[SetupAction] = []
    for target in targets:
        if target == "claude":
            actions += _setup_claude(claude_home, dry_run=dry_run)
        elif target == "codex":
            actions += _setup_codex(codex_home, dry_run=dry_run)
    return SetupReport(dry_run=dry_run, actions=actions)


def _setup_claude(claude_home: Path, *, dry_run: bool) -> list[SetupAction]:
    actions: list[SetupAction] = []
    settings_path = claude_home / "settings.json"
    settings = _load_json(settings_path)
    updated, changes = _merge_claude_settings(settings)
    for change in changes:
        actions.append(SetupAction(target="claude", detail=change, changed=True))
    if changes and not dry_run:
        atomic_write_text(settings_path, json.dumps(updated, indent=2) + "\n")
    if not changes:
        actions.append(
            SetupAction(target="claude", detail="settings already configured", changed=False)
        )
    actions += _install_skills("claude", claude_home, dry_run=dry_run)
    return actions


def _setup_codex(codex_home: Path, *, dry_run: bool) -> list[SetupAction]:
    actions = _install_skills("codex", codex_home, dry_run=dry_run)
    actions.append(
        SetupAction(
            target="codex",
            detail="run `goals context sync` in a project to expose the goal in AGENTS.md",
            changed=False,
        )
    )
    return actions


def _merge_claude_settings(settings: dict) -> tuple[dict, list[str]]:
    """Merge the marketplace + enabled-plugin entries, preserving other keys."""
    changes: list[str] = []
    marketplaces = settings.setdefault("extraKnownMarketplaces", {})
    if marketplaces.get(MARKETPLACE_NAME) != _MARKETPLACE_SOURCE:
        marketplaces[MARKETPLACE_NAME] = _MARKETPLACE_SOURCE
        changes.append(f"registered marketplace '{MARKETPLACE_NAME}' ({MARKETPLACE_REPO})")
    enabled = settings.setdefault("enabledPlugins", {})
    if not enabled.get(PLUGIN_REF):
        enabled[PLUGIN_REF] = True
        changes.append(f"enabled plugin '{PLUGIN_REF}'")
    return settings, changes


def _install_skills(target: str, home: Path, *, dry_run: bool) -> list[SetupAction]:
    skills_dir = home / "skills"
    if dry_run:
        return [
            SetupAction(target=target, detail=f"would install bundled skills into {skills_dir}", changed=False)
        ]
    report = install_bundled_skills([target], target_dirs={target: skills_dir})
    installed = [r for r in report.results if r.status in ("installed", "overwritten")]
    blocked = [r for r in report.results if r.status == "blocked"]
    actions = [
        SetupAction(
            target=target,
            detail=f"installed {len(installed)} bundled skill(s) into {skills_dir}",
            changed=bool(installed),
        )
    ]
    if blocked:
        actions.append(
            SetupAction(
                target=target,
                detail=f"{len(blocked)} skill(s) already present and differ (kept yours)",
                changed=False,
            )
        )
    return actions


def _load_json(path: Path) -> dict:
    """Load an existing settings dict, or {} if the file is absent.

    Critically distinguishes "absent" (safe to create) from "present but
    unreadable/not-an-object" — the latter raises so we NEVER overwrite (and
    destroy) a real settings file we merely failed to parse.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GoalsError(
            f"Could not read {path} ({exc}); refusing to overwrite it. "
            "Fix or move the file, then re-run `goals setup`."
        ) from exc
    if not isinstance(data, dict):
        raise GoalsError(
            f"{path} is not a JSON object; refusing to overwrite it. "
            "Move it aside, then re-run `goals setup`."
        )
    return data


def render_setup_report(report: SetupReport) -> str:
    lines = ["# Goals setup" + (" (dry run)" if report.dry_run else "")]
    for action in report.actions:
        mark = "+" if action.changed else "·"
        lines.append(f"{mark} [{action.target}] {action.detail}")
    if report.dry_run:
        lines.append("\nRe-run without --dry-run to apply.")
    else:
        lines.append("\nDone. In Claude Code, run `/goals:create \"<objective>\"` to begin.")
    return "\n".join(lines)
