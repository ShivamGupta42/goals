from pathlib import Path

from goals.handoffs import analyze_handoff_owners, render_handoff_owner_report
from goals.models import GoalSnapshot, HandoffOwner, WorktreeLease
from goals.runtime import default_phases


def snapshot_with_handoffs(tmp_path: Path, owners: list[HandoffOwner]) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Improve support workflow",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Improve support workflow"),
        current_phase="P1",
        handoff_owners=owners,
    )


def test_handoff_owner_check_passes_for_complete_owner(tmp_path: Path) -> None:
    snapshot = snapshot_with_handoffs(
        tmp_path,
        [
            HandoffOwner(
                label="Support lead",
                role="reviewer",
                responsibility="Review the updated checklist before rollout.",
                owner_type="team",
                phase_ids=["P2"],
                decision_scope=["checklist rollout"],
                escalation_path="Create a follow-up task for the coordinator.",
                confirmation="agent_confirmed",
                status="active",
            )
        ],
    )

    report = analyze_handoff_owners(snapshot)
    rendered = render_handoff_owner_report(report)

    assert report.passed is True
    assert report.user_questions == []
    assert report.agent_actions == []
    assert "Handoff Owner Report" in rendered
    assert "Overall: pass" in rendered


def test_handoff_owner_check_finds_agent_repair_gaps(tmp_path: Path) -> None:
    snapshot = snapshot_with_handoffs(
        tmp_path,
        [
            HandoffOwner(
                label="Ops reviewer",
                owner_type="team",
                phase_ids=["P9"],
            )
        ],
    )

    report = analyze_handoff_owners(snapshot)

    assert report.passed is False
    assert report.user_questions == []
    assert any("missing a responsibility" in finding.summary for finding in report.findings)
    assert any("unknown phases" in finding.summary for finding in report.findings)
    assert any("escalation path" in finding.summary for finding in report.findings)
    assert any("Record the specific work" in action for action in report.agent_actions)


def test_handoff_owner_check_surfaces_explicit_user_confirmation(tmp_path: Path) -> None:
    snapshot = snapshot_with_handoffs(
        tmp_path,
        [
            HandoffOwner(
                label="User",
                role="approver",
                responsibility="Approve the new accountability owner.",
                owner_type="user",
                confirmation="needs_user",
                status="proposed",
            ),
            HandoffOwner(
                label="Blocked rollout owner",
                role="owner",
                responsibility="Own rollout after merge.",
                owner_type="team",
                escalation_path="Ask the coordinator.",
                status="blocked",
            ),
        ],
    )

    report = analyze_handoff_owners(snapshot)

    assert report.passed is False
    assert any("needs user confirmation" in question for question in report.user_questions)
    assert any("is blocked" in question for question in report.user_questions)
    assert any(finding.needs_user for finding in report.findings)


def test_handoff_owner_check_is_quiet_until_handoffs_exist(tmp_path: Path) -> None:
    snapshot = snapshot_with_handoffs(tmp_path, [])

    report = analyze_handoff_owners(snapshot)

    assert report.passed is True
    assert report.findings == []
    assert report.user_questions == []
