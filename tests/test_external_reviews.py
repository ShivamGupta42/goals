from pathlib import Path

from goals.external_reviews import analyze_external_reviews, render_external_review_report
from goals.models import ExternalReview, GoalSnapshot, WorktreeLease
from goals.runtime import default_phases


def snapshot_with_reviews(
    tmp_path: Path,
    reviews: list[ExternalReview],
    objective: str = "Improve support workflow",
) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective=objective,
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases(objective),
        current_phase="P1",
        external_reviews=reviews,
    )


def test_external_review_check_is_quiet_until_needed(tmp_path: Path) -> None:
    snapshot = snapshot_with_reviews(tmp_path, [])

    report = analyze_external_reviews(snapshot)
    rendered = render_external_review_report(report)

    assert report.passed is True
    assert report.findings == []
    assert report.user_questions == []
    assert "External Review Report" in rendered
    assert "Overall: pass" in rendered


def test_high_stakes_goal_without_review_surfaces_user_decision(tmp_path: Path) -> None:
    snapshot = snapshot_with_reviews(tmp_path, [], objective="Plan a medical safety decision")

    report = analyze_external_reviews(snapshot)

    assert report.passed is False
    assert report.high_stakes_domains == ["medical", "safety"]
    assert any(finding.severity == "p0" for finding in report.findings)
    assert any(finding.needs_user for finding in report.findings)
    assert any("External review is required" in question for question in report.user_questions)


def test_passed_external_review_requires_summary_and_evidence(tmp_path: Path) -> None:
    snapshot = snapshot_with_reviews(
        tmp_path,
        [
            ExternalReview(
                title="Security review",
                reviewer="Security lead",
                reviewer_type="security",
                risk_domain="security",
                status="passed",
                phase_ids=["P2"],
                scope=["Prompt injection checks"],
            )
        ],
    )

    report = analyze_external_reviews(snapshot)

    assert report.passed is False
    assert report.user_questions == []
    assert any("no summary" in finding.summary for finding in report.findings)
    assert any("no evidence reference" in finding.summary for finding in report.findings)
    assert any("Record what the reviewer approved" in action for action in report.agent_actions)


def test_complete_passed_external_review_passes(tmp_path: Path) -> None:
    snapshot = snapshot_with_reviews(
        tmp_path,
        [
            ExternalReview(
                title="Security review",
                reviewer="Security lead",
                reviewer_type="security",
                risk_domain="security",
                status="passed",
                phase_ids=["P2"],
                scope=["Prompt injection checks"],
                summary="Security lead approved the prompt injection mitigation.",
                evidence_refs=["evidence:P2"],
            )
        ],
    )

    report = analyze_external_reviews(snapshot)

    assert report.passed is True
    assert report.user_questions == []
    assert report.agent_actions == []


def test_blocked_failed_and_high_risk_waived_review_need_user(tmp_path: Path) -> None:
    snapshot = snapshot_with_reviews(
        tmp_path,
        [
            ExternalReview(
                title="Legal review",
                reviewer="Counsel",
                reviewer_type="legal",
                risk_domain="legal",
                status="failed",
                scope=["Terms change"],
            ),
            ExternalReview(
                title="Security review",
                reviewer_type="security",
                risk_domain="security",
                status="blocked",
                scope=["Deployment risk"],
            ),
            ExternalReview(
                title="Medical review",
                reviewer="User",
                reviewer_type="user",
                risk_domain="medical",
                status="waived",
                scope=["Health advice"],
                waiver_reason="User wants to proceed without review.",
            ),
        ],
    )

    report = analyze_external_reviews(snapshot)

    assert report.passed is False
    assert any("failed" in question for question in report.user_questions)
    assert any("blocked" in question for question in report.user_questions)
    assert any("waived" in question for question in report.user_questions)
