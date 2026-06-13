from pathlib import Path

import pytest

from goals.discovery import discover_local_ecosystem, render_discovery_report
from goals.ecosystem import recommend_ecosystem_tools, render_recommendations
from goals.registry_sync import apply_registry_sync, plan_registry_sync
from goals.models import GoalSnapshot, WorktreeLease
from goals.registry import validate_registry_file
from goals.runtime import default_phases
from goals.storage import GoalsError


def test_ecosystem_recommendations_match_goal_phase_and_project_signals(tmp_path: Path) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "tests").mkdir()
    (registry_root / "skills.yml").write_text(
        """
version: 1
kind: skills
skills:
  decision-explainer:
    label: Decision Explainer
    description: Explain risky technical tradeoffs.
    use_when: [migration, risk, decision]
    phases: [P2]
    command_hint: goals decision explain --file decision.json --level basic
  testing:
    label: Testing
    description: Prove implementation with tests.
    use_when: [pytest, tests, proof]
    phases: [P3, P4]
"""
    )
    (registry_root / "plugins.yml").write_text(
        """
version: 1
kind: plugins
plugins:
  browser:
    label: Browser
    description: Inspect local dashboards.
    use_when: [dashboard, html, visual]
    phases: [P4]
"""
    )
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Explain migration risk and update tests",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Explain migration risk and update tests"),
        current_phase="P2",
    )

    recommendations = recommend_ecosystem_tools(tmp_path, snapshot, limit=2)
    rendered = render_recommendations(recommendations)

    assert recommendations[0].name == "decision-explainer"
    assert recommendations[0].kind == "skill"
    assert recommendations[0].source_registry == "skills.yml"
    assert "migration" in recommendations[0].reason
    assert "goals decision explain" in rendered


def test_registry_validation_rejects_unknown_skill_entry_field(tmp_path: Path) -> None:
    path = tmp_path / "skills.yml"
    path.write_text(
        """
version: 1
kind: skills
skills:
  bad:
    label: Bad
    shell: rm -rf .
"""
    )

    with pytest.raises(GoalsError):
        validate_registry_file(path)


def test_discovery_finds_local_skills_without_leaking_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    (registry_root / "skills.yml").write_text(
        "version: 1\nkind: skills\nskills:\n  decision-explainer:\n    label: Decision Explainer\n"
    )
    (registry_root / "adapters.yml").write_text(
        "version: 1\nkind: adapters\nadapters:\n  claude:\n    label: Claude\n"
    )
    skill_root = tmp_path / "local-skills"
    skill = skill_root / "migration-helper"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        """---
name: Migration Helper
description: Helps coordinate database migrations safely.
---

# Migration Helper
"""
    )
    monkeypatch.setattr("goals.discovery.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("goals.discovery.adapter_check", lambda name: (name == "claude", "ok"))

    report = discover_local_ecosystem(tmp_path, skill_roots=[skill_root])
    rendered = render_discovery_report(report)

    discovered = {tool.name: tool for tool in report.tools}
    assert discovered["migration-helper"].registered is False
    assert discovered["migration-helper"].suggested_registry_entry["migration-helper"]["label"] == (
        "Migration Helper"
    )
    assert discovered["claude"].registered is True
    assert "migration-helper" in rendered
    assert str(tmp_path) not in rendered


def test_discovery_json_is_sanitized(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    skill = skill_root / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: Review\ndescription: Reviews source changes.\n---\n"
    )
    monkeypatch.setattr("goals.discovery.shutil.which", lambda name: None)

    report = discover_local_ecosystem(tmp_path, skill_roots=[skill_root])

    assert str(tmp_path) not in report.model_dump_json()
    assert report.missing_from_registry


def test_registry_sync_dry_run_and_apply(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    (registry_root / "skills.yml").write_text("version: 1\nkind: skills\nskills: {}\n")
    (registry_root / "adapters.yml").write_text("version: 1\nkind: adapters\nadapters: {}\n")
    skill_root = tmp_path / "skills"
    skill = skill_root / "migration-helper"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: Migration Helper\n"
        "description: Helps coordinate database migrations safely.\n---\n"
    )
    monkeypatch.setattr("goals.discovery.shutil.which", lambda name: None)

    plan = plan_registry_sync(tmp_path, skill_roots=[skill_root])

    assert plan.dry_run is True
    assert any(change.name == "migration-helper" for change in plan.changes)
    assert "migration-helper" not in (registry_root / "skills.yml").read_text()

    applied = apply_registry_sync(tmp_path, plan)

    assert applied.dry_run is False
    text = (registry_root / "skills.yml").read_text()
    assert "migration-helper" in text
    assert str(tmp_path) not in text
    validate_registry_file(registry_root / "skills.yml")
