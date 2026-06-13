from pathlib import Path

from goals.evaluations import DEFAULT_GOAL_SCENARIOS, evaluate_goal_scenarios


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
    for name in ("adapters.yml", "agents.yml", "gates.yml", "profiles.yml", "skills.yml"):
        (registry_root / name).write_text("version: 1\nkind: profiles\nprofiles: {}\n")
    monkeypatch.setattr("goals.mode_a.adapter_check", lambda name: (True, f"{name} ready"))

    results = evaluate_goal_scenarios(tmp_path, adapter="claude")

    assert all(result.current_supported for result in results)
    assert any("architecture_map" in result.planned_capabilities for result in results)
    assert any("automatic_skill_selection" in result.planned_capabilities for result in results)
    for result in results:
        assert "end_user_decision_experience" in result.supported_capabilities
        assert result.surfaced_decisions
        assert all(decision.priority == "blocking" for decision in result.surfaced_decisions)
        assert result.agent_decisions
