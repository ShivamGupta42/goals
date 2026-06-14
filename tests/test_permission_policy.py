from pathlib import Path

import pytest

from goals.permission_policy import decide_permission
from goals.registry import validate_registry_file
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
