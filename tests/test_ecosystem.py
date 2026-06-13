from pathlib import Path

import pytest

from goals.discovery import discover_local_ecosystem, render_discovery_report
from goals.ecosystem import (
    merge_agent_recommendations,
    recommend_ecosystem_tools,
    render_recommendation_merge_report,
    render_recommendations,
)
from goals.ecosystem_quality import audit_ecosystem_quality, render_ecosystem_quality_report
from goals.models import (
    AgentRecommendationSet,
    EcosystemRecommendation,
    GoalSnapshot,
    WorktreeLease,
)
from goals.registry import validate_registry_file
from goals.registry_sync import apply_registry_sync, plan_registry_sync
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


def test_merge_agent_recommendations_ranks_consensus_and_surfaces_approval() -> None:
    claude = AgentRecommendationSet(
        agent_id="claude",
        adapter="claude",
        recommendations=[
            _recommendation("skill", "testing", confidence=0.7),
            _recommendation("plugin", "browser", confidence=0.6, approval=True),
        ],
    )
    codex = AgentRecommendationSet(
        agent_id="codex",
        adapter="codex",
        recommendations=[
            _recommendation("skill", "testing", confidence=0.9),
            _recommendation("skill", "docs", confidence=0.4),
        ],
    )

    report = merge_agent_recommendations([claude, codex])
    rendered = render_recommendation_merge_report(report)

    assert report.agent_count == 2
    assert report.recommendations[0].name == "testing"
    assert report.recommendations[0].support_count == 2
    assert report.recommendations[0].agent_ids == ["claude", "codex"]
    assert "Approve use of plugin browser?" in report.user_questions
    assert "No tool-routing decision" not in rendered
    assert "supported by 2 agent(s)" in rendered


def test_merge_agent_recommendations_keeps_command_conflict_with_agent() -> None:
    local_hint = "/" + "Users" + "/example/private/run-browser"
    claude = AgentRecommendationSet(
        agent_id="claude",
        recommendations=[_recommendation("plugin", "browser", command_hint=local_hint)],
    )
    codex = AgentRecommendationSet(
        agent_id="codex",
        recommendations=[_recommendation("plugin", "browser", command_hint="goals dashboard")],
    )

    report = merge_agent_recommendations([claude, codex])
    rendered = render_recommendation_merge_report(report)

    assert report.conflicts
    assert report.conflicts[0].needs_user is False
    assert report.user_questions == []
    assert any("Resolve routing conflict" in action for action in report.agent_actions)
    assert "/" + "Users" + "/example" not in rendered
    assert "~" in rendered


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


def test_ecosystem_quality_audit_passes_builtin_registries(tmp_path: Path) -> None:
    report = audit_ecosystem_quality(tmp_path)
    rendered = render_ecosystem_quality_report(report)

    assert report.passed is True
    assert report.entry_count > 0
    assert not [finding for finding in report.findings if finding.severity in {"p0", "p1"}]
    assert "Ecosystem Quality Audit" in rendered
    assert "SkillOpt-style loop" in rendered


def test_ecosystem_quality_audit_flags_unsafe_and_vague_entries(tmp_path: Path) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    local_path_hint = "/" + "Users" + "/example/private/run-cleanup"
    (registry_root / "skills.yml").write_text(
        """
version: 1
kind: skills
skills:
  vague-helper:
    label: Helper
    description: Helps.
    use_when: [anything, everything]
    risk: low
    requires_user_approval: false
"""
    )
    (registry_root / "plugins.yml").write_text(
        f"""
version: 1
kind: plugins
plugins:
  dangerous-plugin:
    label: Dangerous Plugin
    description: Deletes remote resources for cleanup goals.
    use_when: [cleanup, deletion, remote resources]
    phases: [P3]
    command_hint: {local_path_hint}
    risk: high
    requires_user_approval: false
"""
    )

    report = audit_ecosystem_quality(tmp_path)
    rendered = render_ecosystem_quality_report(report)

    assert report.passed is False
    assert any(finding.area == "routing" for finding in report.findings)
    assert any(finding.area == "safety" and finding.severity == "p0" for finding in report.findings)
    assert "High-risk plugins must require user approval" in rendered
    assert "/" + "Users" + "/example" not in rendered
    assert "command_hint contains local path" in rendered


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


def test_discovery_finds_local_plugins_without_leaking_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    (registry_root / "plugins.yml").write_text("version: 1\nkind: plugins\nplugins: {}\n")
    plugin_root = tmp_path / "local-plugins"
    plugin = plugin_root / "customer-research" / ".codex-plugin"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        """
{
  "name": "@acme/customer-research",
  "displayName": "Customer Research",
  "description": "Finds and summarizes customer research sources.",
  "keywords": ["research", "sources"]
}
"""
    )
    monkeypatch.setattr("goals.discovery.shutil.which", lambda name: None)

    report = discover_local_ecosystem(tmp_path, plugin_roots=[plugin_root])
    rendered = render_discovery_report(report)

    discovered = {tool.name: tool for tool in report.tools}
    assert discovered["customer-research"].kind == "plugin"
    assert discovered["customer-research"].registered is False
    entry = discovered["customer-research"].suggested_registry_entry["customer-research"]
    assert entry["label"] == "Customer Research"
    assert entry["requires_user_approval"] is True
    assert "research" in entry["use_when"]
    assert "customer-research" in rendered
    assert str(tmp_path) not in rendered
    assert str(tmp_path) not in report.model_dump_json()


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
    (registry_root / "plugins.yml").write_text("version: 1\nkind: plugins\nplugins: {}\n")
    (registry_root / "adapters.yml").write_text("version: 1\nkind: adapters\nadapters: {}\n")
    skill_root = tmp_path / "skills"
    skill = skill_root / "migration-helper"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: Migration Helper\n"
        "description: Helps coordinate database migrations safely.\n---\n"
    )
    plugin_root = tmp_path / "plugins"
    plugin = plugin_root / "customer-research"
    plugin.mkdir(parents=True)
    (plugin / "package.json").write_text(
        """
{
  "name": "@acme/customer-research",
  "description": "Finds customer research sources."
}
"""
    )
    monkeypatch.setattr("goals.discovery.shutil.which", lambda name: None)

    plan = plan_registry_sync(tmp_path, skill_roots=[skill_root], plugin_roots=[plugin_root])

    assert plan.dry_run is True
    assert any(change.name == "migration-helper" for change in plan.changes)
    assert any(change.name == "customer-research" for change in plan.changes)
    assert "migration-helper" not in (registry_root / "skills.yml").read_text()
    assert "customer-research" not in (registry_root / "plugins.yml").read_text()

    applied = apply_registry_sync(tmp_path, plan)

    assert applied.dry_run is False
    skills_text = (registry_root / "skills.yml").read_text()
    plugins_text = (registry_root / "plugins.yml").read_text()
    assert "migration-helper" in skills_text
    assert "customer-research" in plugins_text
    assert "requires_user_approval: true" in plugins_text
    assert str(tmp_path) not in skills_text
    assert str(tmp_path) not in plugins_text
    validate_registry_file(registry_root / "skills.yml")
    validate_registry_file(registry_root / "plugins.yml")


def _recommendation(
    kind: str,
    name: str,
    *,
    confidence: float = 0.5,
    approval: bool = False,
    command_hint: str = "",
) -> EcosystemRecommendation:
    return EcosystemRecommendation(
        kind=kind,  # type: ignore[arg-type]
        name=name,
        label=name.title(),
        reason=f"Matches {name}.",
        confidence=confidence,
        command_hint=command_hint,
        source_registry=f"{kind}s.yml",
        user_approval_required=approval,
    )
