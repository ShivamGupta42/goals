from pathlib import Path

from goals.evaluations import (
    DEFAULT_GOAL_SCENARIOS,
    dogfood_goal_scenarios,
    evaluate_goal_scenarios,
    render_dogfood_report,
)


def test_default_scenarios_cover_core_goal_types() -> None:
    categories = {scenario.category for scenario in DEFAULT_GOAL_SCENARIOS}
    assert categories == {"personal", "technical", "business", "self_evolution", "ecosystem"}


def test_goal_scenarios_are_supported_by_current_mode_a(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[dependency-groups]\ndev = ['pytest', 'ruff']\n"
    )
    (tmp_path / "tests").mkdir()
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    for name in (
        "adapters.yml",
        "agents.yml",
        "gates.yml",
        "plugins.yml",
        "profiles.yml",
        "skills.yml",
    ):
        (registry_root / name).write_text("version: 1\nkind: profiles\nprofiles: {}\n")
    monkeypatch.setattr("goals.mode_a.adapter_check", lambda name: (True, f"{name} ready"))

    results = evaluate_goal_scenarios(tmp_path, adapter="claude")

    assert all(result.current_supported for result in results)
    assert any("architecture_map" in result.supported_capabilities for result in results)
    assert all("architecture_map" not in result.planned_capabilities for result in results)
    assert any("automatic_skill_selection" in result.supported_capabilities for result in results)
    assert all("automatic_skill_selection" not in result.planned_capabilities for result in results)
    assert any("local_ecosystem_discovery" in result.supported_capabilities for result in results)
    assert any("plugin_capability_discovery" in result.supported_capabilities for result in results)
    assert any("registry_sync_workflow" in result.supported_capabilities for result in results)
    assert any("self_evolution_memory" in result.supported_capabilities for result in results)
    assert all("self_evolution_memory" not in result.planned_capabilities for result in results)
    assert any("source_registry" in result.supported_capabilities for result in results)
    assert all("source_registry" not in result.planned_capabilities for result in results)
    assert all(
        "plugin_capability_discovery" not in result.planned_capabilities for result in results
    )
    for result in results:
        assert "end_user_decision_experience" in result.supported_capabilities
        assert result.surfaced_decisions
        assert all(decision.priority == "blocking" for decision in result.surfaced_decisions)
        assert result.agent_decisions
    personal = next(result for result in results if result.scenario_id == "personal-fitness-reset")
    assert "project_history_decision_context" in personal.supported_capabilities
    assert "project_history_decision_context" not in personal.planned_capabilities


def test_dogfood_report_checks_decision_burden_and_evidence(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    for name, kind in {
        "adapters.yml": "adapters",
        "agents.yml": "agents",
        "gates.yml": "gates",
        "plugins.yml": "plugins",
        "profiles.yml": "profiles",
        "skills.yml": "skills",
    }.items():
        (registry_root / name).write_text(f"version: 1\nkind: {kind}\n{kind}: {{}}\n")
    monkeypatch.setattr("goals.mode_a.adapter_check", lambda name: (True, f"{name} ready"))

    report = dogfood_goal_scenarios(tmp_path, adapter="claude")
    rendered = render_dogfood_report(report)

    assert report.passed is True
    assert len(report.cases) == 5
    assert all(case.user_decision_count == 1 for case in report.cases)
    assert all(case.agent_decision_count >= 3 for case in report.cases)
    assert all(case.required_evidence for case in report.cases)
    assert "Goals Dogfood Report" in rendered
    assert "What the user sees" in rendered
    assert "What the agent can decide" in rendered
    assert "Proof required" in rendered
    assert "May the agent use an external plugin" in rendered
