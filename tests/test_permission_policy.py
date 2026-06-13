from pathlib import Path

import pytest

from goals.ecosystem import (
    merge_agent_recommendations,
    recommend_ecosystem_tools,
    render_recommendation_merge_report,
)
from goals.models import (
    AgentRecommendationSet,
    EcosystemRecommendation,
    GoalSnapshot,
    WorktreeLease,
)
from goals.permission_policy import (
    decide_permission,
    render_permission_report,
    permission_report_for_recommendations,
)
from goals.registry import validate_registry_file
from goals.runtime import default_phases
from goals.storage import GoalsError


def test_builtin_permission_policy_marks_external_connectors_as_user_decisions(
    tmp_path: Path,
) -> None:
    decision = decide_permission(
        tmp_path,
        subject_kind="plugin",
        subject_name="github",
        action="inspect a remote issue",
        reason="Remote connector can expose account context.",
    )

    assert decision.decision == "ask_user"
    assert decision.needs_user is True
    assert decision.unsafe is False
    assert decision.policy_id == "external-service"
    assert "external service" in decision.user_question.lower()


def test_project_permission_policy_overrides_builtin_defaults(tmp_path: Path) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    (registry_root / "permissions.yml").write_text(
        """
version: 1
kind: permissions
permissions:
  local-browser:
    label: Local Browser
    description: Local browser inspection is allowed for this project.
    match: [browser, local dashboard]
    decision: allow
    risk: low
    agent_action: Inspect the local dashboard and record evidence.
"""
    )

    decision = decide_permission(
        tmp_path,
        subject_kind="plugin",
        subject_name="browser",
        action="inspect local dashboard",
    )

    assert decision.decision == "allow"
    assert decision.needs_user is False
    assert decision.policy_id == "local-browser"
    assert "Inspect the local dashboard" in decision.agent_action


def test_destructive_permission_policy_beats_external_service_match(tmp_path: Path) -> None:
    decision = decide_permission(
        tmp_path,
        subject_kind="command",
        subject_name="gh api",
        action="delete production resources through github",
    )

    assert decision.decision == "deny"
    assert decision.unsafe is True
    assert decision.policy_id == "destructive-or-costly"


def test_permission_policy_uses_token_matches_for_short_terms(tmp_path: Path) -> None:
    decision = decide_permission(
        tmp_path,
        subject_kind="skill",
        subject_name="decision-explainer",
        reason="Explain a decision in simple language.",
    )

    assert decision.decision == "agent_decide"
    assert decision.policy_id == "repo-local-safe"


def test_permission_report_for_recommendations_is_plain_and_actionable(tmp_path: Path) -> None:
    report = permission_report_for_recommendations(
        tmp_path,
        [
            EcosystemRecommendation(
                kind="plugin",
                name="github",
                label="GitHub",
                reason="Remote issue context matters.",
                source_registry="plugins.yml",
            )
        ],
    )
    rendered = render_permission_report(report)

    assert report.user_questions == ["Approve use of this external service or connector?"]
    assert "Permission Policy Report" in rendered
    assert "Needs The User" in rendered
    assert "Approve use of this external service" in rendered


def test_ecosystem_recommendations_apply_permission_policy(tmp_path: Path) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    (registry_root / "plugins.yml").write_text(
        """
version: 1
kind: plugins
plugins:
  github:
    label: GitHub
    description: Inspect remote issues and CI failures.
    use_when: [github, issue, ci]
    phases: [P1]
    command_hint: Use the GitHub connector.
    risk: low
    requires_user_approval: false
"""
    )
    (registry_root / "skills.yml").write_text("version: 1\nkind: skills\nskills: {}\n")
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Use github issue context to plan the next phase.",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Use github issue context to plan the next phase."),
        current_phase="P1",
    )

    recommendations = recommend_ecosystem_tools(tmp_path, snapshot, limit=1)

    assert recommendations[0].name == "github"
    assert recommendations[0].user_approval_required is True
    assert "Permission policy `external-service` says ask_user" in recommendations[0].reason


def test_merge_agent_recommendations_can_apply_permission_policy(tmp_path: Path) -> None:
    recommendation_set = AgentRecommendationSet(
        agent_id="claude",
        recommendations=[
            EcosystemRecommendation(
                kind="plugin",
                name="github",
                label="GitHub",
                reason="Inspect issue history.",
                source_registry="plugins.yml",
            )
        ],
    )

    report = merge_agent_recommendations([recommendation_set], worktree=tmp_path)
    rendered = render_recommendation_merge_report(report)

    assert report.recommendations[0].user_approval_required is True
    assert report.user_questions == ["Approve use of plugin github?"]
    assert "User approval required" in rendered


def test_permission_registry_rejects_unknown_entry_fields(tmp_path: Path) -> None:
    path = tmp_path / "permissions.yml"
    path.write_text(
        """
version: 1
kind: permissions
permissions:
  bad:
    label: Bad
    description: Bad policy.
    shell: rm -rf .
"""
    )

    with pytest.raises(GoalsError):
        validate_registry_file(path)
