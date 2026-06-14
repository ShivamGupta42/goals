from pathlib import Path

import pytest

from goals.ecosystem import (
    merge_agent_recommendations,
    recommend_ecosystem_tools,
    render_recommendation_merge_report,
    render_recommendations,
)
from goals.models import (
    AgentRecommendationSet,
    EcosystemRecommendation,
    GoalSnapshot,
    WorktreeLease,
)
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
