from pathlib import Path

from goals.evaluations import (
    DEFAULT_GOAL_SCENARIOS,
    DEFAULT_GOAL_USE_CASES,
    dogfood_goal_scenarios,
    evaluate_goal_scenarios,
    evaluate_use_case_coverage,
    rehearse_goal_lifecycles,
    render_coverage_report,
    render_dogfood_report,
    render_issue_stress_report,
    render_rehearsal_report,
    render_self_check_report,
    run_self_check,
    stress_goal_issue_discovery,
)


def test_default_scenarios_cover_core_goal_types() -> None:
    categories = {scenario.category for scenario in DEFAULT_GOAL_SCENARIOS}
    assert categories == {"personal", "technical", "business", "self_evolution", "ecosystem"}


def test_default_use_cases_cover_broad_goal_families() -> None:
    categories = {use_case.category for use_case in DEFAULT_GOAL_USE_CASES}
    assert {
        "personal",
        "technical",
        "business",
        "research",
        "creative",
        "operations",
        "high_stakes",
        "ecosystem",
        "self_evolution",
    }.issubset(categories)


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
    assert any("permission_policy_registry" in result.supported_capabilities for result in results)
    assert any("registry_sync_workflow" in result.supported_capabilities for result in results)
    assert any("issue_discovery" in result.supported_capabilities for result in results)
    assert any("self_evolution_memory" in result.supported_capabilities for result in results)
    assert all("self_evolution_memory" not in result.planned_capabilities for result in results)
    assert any("source_registry" in result.supported_capabilities for result in results)
    assert all("source_registry" not in result.planned_capabilities for result in results)
    assert any("source_freshness_gate" in result.supported_capabilities for result in results)
    assert all("source_freshness_gate" not in result.planned_capabilities for result in results)
    assert all(
        "plugin_capability_discovery" not in result.planned_capabilities for result in results
    )
    assert all(
        "permission_policy_registry" not in result.planned_capabilities for result in results
    )
    for result in results:
        assert "end_user_decision_experience" in result.supported_capabilities
        assert result.surfaced_decisions
        assert all(decision.priority == "blocking" for decision in result.surfaced_decisions)
        assert result.agent_decisions
    personal = next(result for result in results if result.scenario_id == "personal-fitness-reset")
    assert "project_history_decision_context" in personal.supported_capabilities
    assert "project_history_decision_context" not in personal.planned_capabilities


def test_use_case_coverage_reports_broad_current_and_future_fit(
    monkeypatch, tmp_path: Path
) -> None:
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

    report = evaluate_use_case_coverage(tmp_path, adapter="claude")
    rendered = render_coverage_report(report)

    assert report.passed is True
    assert len(report.cases) >= 9
    assert all(case.status == "covered" for case in report.cases)
    assert any(case.category == "high_stakes" for case in report.cases)
    assert any(
        "professional_boundary_templates" in case.planned_capabilities for case in report.cases
    )
    assert "Goal Use-Case Coverage Report" in rendered
    assert "Important User Decisions" in rendered
    assert "Capability Coverage" in rendered
    assert "high-stakes-boundary" in rendered


def test_rehearsal_runs_real_temporary_goal_lifecycles() -> None:
    report = rehearse_goal_lifecycles(scenarios=DEFAULT_GOAL_SCENARIOS[:3])
    rendered = render_rehearsal_report(report)

    assert report.passed is True
    assert len(report.cases) == 3
    assert all(case.status == "pass" for case in report.cases)
    assert all(case.phases_accepted == 4 for case in report.cases)
    assert all(case.dashboard_rendered for case in report.cases)
    assert all(case.issue_count == 0 for case in report.cases)
    assert "Goal Lifecycle Rehearsal Report" in rendered
    assert "business-research-brief: pass" in rendered


def test_issue_stress_checks_repair_actions_and_user_decision_filter(tmp_path: Path) -> None:
    report = stress_goal_issue_discovery(tmp_path)
    rendered = render_issue_stress_report(report)

    assert report.passed is True
    assert len(report.cases) == 5
    assert all(case.passed for case in report.cases)
    agent_repair = next(case for case in report.cases if case.stress_id == "agent-repair-no-user")
    assert agent_repair.user_questions == []
    assert agent_repair.agent_action_count >= 3
    decision_filter = next(case for case in report.cases if case.stress_id == "decision-filter")
    assert decision_filter.user_questions == ["Choose whether a data migration is allowed."]
    assert decision_filter.unexpected_user_questions == []
    merge_readiness = next(case for case in report.cases if case.stress_id == "merge-readiness")
    assert merge_readiness.user_questions == []
    assert merge_readiness.agent_action_count >= 1
    assert "Goal Issue Stress Report" in rendered
    assert "unsafe-review-escalation: pass" in rendered


def test_self_check_summarizes_all_evaluation_suites(monkeypatch, tmp_path: Path) -> None:
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

    report = run_self_check(tmp_path, adapters=["claude"])
    rendered = render_self_check_report(report)

    assert report.passed is True
    assert len(report.adapters) == 1
    result = report.adapters[0]
    assert result.adapter == "claude"
    assert result.scenarios_passed is True
    assert result.dogfood_passed is True
    assert result.coverage_passed is True
    assert result.rehearsal_passed is True
    assert result.issue_stress_passed is True
    assert result.user_decision_count == 5
    assert result.agent_repair_action_count >= 1
    assert report.next_slices
    assert report.next_slices[0] == "Explore planned capability: cross-project memory sync"
    assert "Goals Self-Check Report" in rendered
    assert "Recommended Next Slices" in rendered
    assert "User Experience Findings" in rendered


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
