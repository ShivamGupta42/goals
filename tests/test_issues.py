from goals.issues import analyze_goal_issues, render_issue_report
from goals.models import (
    Decision,
    DecisionOption,
    Evidence,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    Phase,
    PhaseStatus,
    SourceClaim,
    WorktreeLease,
)


def test_issue_report_finds_blockers_missing_proof_and_user_decisions(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add tags to tasks",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Plan",
                goal="Plan the work",
                status=PhaseStatus.NEEDS_REVIEW,
                evidence=Evidence(
                    acceptance_not_met=["Definition of done unclear."],
                    ambiguous=["Migration risk unclear."],
                    confidence=0.4,
                    notes="Partial evidence.",
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.FAIL,
                        summary="Evidence is incomplete.",
                    )
                ],
            )
        ],
        current_phase="P1",
        decisions=[
            Decision(
                title="Migration choice",
                plain_summary="Choose whether a migration is allowed.",
                why_it_matters="Data changes may be hard to reverse.",
                recommendation="Avoid migration",
                options=[
                    DecisionOption(
                        label="Add migration",
                        explanation="Change storage shape.",
                        risk="high",
                        reversible=False,
                    )
                ],
                priority="blocking",
                suggested_reply="Avoid migration",
            )
        ],
        source_claims=[
            SourceClaim(claim="Users need tags.", source_ids=["SRC-missing"], confidence=0.4)
        ],
    )

    report = analyze_goal_issues(snapshot)
    rendered = render_issue_report(report)

    assert report.passed is False
    assert any(issue.area == "decision" and issue.needs_user for issue in report.issues)
    assert any(issue.area == "evidence" for issue in report.issues)
    assert any(issue.area == "gate" for issue in report.issues)
    assert any(issue.area == "source" for issue in report.issues)
    assert "Choose whether a migration is allowed." in report.user_questions
    assert "Goal Issue Report" in rendered
    assert "Needs The User" in rendered
    assert "Agent Can Work On" in rendered


def test_clean_goal_has_no_issue_findings(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Finish demo",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Done",
                goal="Prove the work",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    checks_run=["pytest"],
                    acceptance_met=["done"],
                    confidence=0.9,
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.PASS,
                        summary="ok",
                    )
                ],
            )
        ],
        current_phase=None,
        status="complete",
        definition_of_done=["Done"],
    )

    report = analyze_goal_issues(snapshot)

    assert report.passed is True
    assert report.issues == []
