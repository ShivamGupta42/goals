from goals.issues import analyze_goal_issues, render_issue_report
from goals.models import (
    ArchitectureNode,
    AssetRecord,
    Decision,
    DecisionOption,
    Evidence,
    ExternalReview,
    GateResult,
    GateVerdict,
    GoalArchitectureMap,
    GoalSnapshot,
    Phase,
    PhaseStatus,
    SourceClaim,
    SourceRecord,
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
    assert any(issue.area == "citation" for issue in report.issues)
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


def test_issue_report_includes_external_review_blockers(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Update legal terms",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Review terms",
                goal="Check legal risk",
                status=PhaseStatus.IN_PROGRESS,
            )
        ],
        current_phase="P1",
        external_reviews=[
            ExternalReview(
                title="Legal review",
                reviewer="Counsel",
                reviewer_type="legal",
                risk_domain="legal",
                status="failed",
                scope=["Terms update"],
            )
        ],
    )

    report = analyze_goal_issues(snapshot)
    rendered = render_issue_report(report)

    assert report.passed is False
    assert any(issue.area == "external_review" and issue.needs_user for issue in report.issues)
    assert any("External review failed" in question for question in report.user_questions)
    assert "[external_review user]" in rendered


def test_issue_report_includes_stale_source_as_agent_repair(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Prepare customer research brief",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[],
        current_phase=None,
        definition_of_done=["Done"],
        sources=[
            SourceRecord(
                source_id="SRC-old",
                title="Old research note",
                source_type="url",
                added_at="2000-01-01T00:00:00+00:00",
            )
        ],
        source_claims=[
            SourceClaim(
                claim="Customers want simpler status.",
                source_ids=["SRC-old"],
                confidence=0.8,
            )
        ],
    )

    report = analyze_goal_issues(snapshot)

    assert any(issue.summary == "Source may be stale: Old research note" for issue in report.issues)
    assert "Source may be stale: Old research note" not in report.user_questions
    assert any("Refresh, replace, or mark this source" in action for action in report.agent_actions)


def test_issue_report_surfaces_high_stakes_stale_source(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Prepare legal safety brief",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[],
        current_phase=None,
        definition_of_done=["Done"],
        sources=[
            SourceRecord(
                source_id="SRC-old",
                title="Old legal memo",
                source_type="document",
                added_at="2000-01-01T00:00:00+00:00",
            )
        ],
        source_claims=[
            SourceClaim(
                claim="A legal conclusion is safe.",
                source_ids=["SRC-old"],
                confidence=0.9,
            )
        ],
    )

    report = analyze_goal_issues(snapshot)

    assert "Source may be stale: Old legal memo" in report.user_questions


def test_issue_report_surfaces_high_stakes_weak_citation(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Prepare legal safety brief",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[],
        current_phase=None,
        definition_of_done=["Done"],
        sources=[
            SourceRecord(
                source_id="SRC-blog",
                title="Legal blog",
                locator="https://example.test/legal",
                source_type="url",
                summary="Informal commentary.",
                credibility="low",
            )
        ],
        source_claims=[
            SourceClaim(
                claim="The legal conclusion is safe.",
                source_ids=["SRC-blog"],
                confidence=0.9,
            )
        ],
    )

    report = analyze_goal_issues(snapshot)

    assert (
        "High-confidence claim relies only on low-credibility sources: The legal conclusion is safe."
        in report.user_questions
    )
    assert any(issue.area == "citation" and issue.needs_user for issue in report.issues)


def test_issue_report_includes_code_architecture_mismatch(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "storage.py").write_text("def save(): pass\n")
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Ship storage",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Update storage",
                goal="Change storage.",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    changed_files=["src/storage.py"],
                    checks_run=["pytest"],
                    acceptance_met=["Storage changed."],
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
        current_phase="P1",
        definition_of_done=["Done"],
        architecture=GoalArchitectureMap(
            title="Demo map",
            overview="Does not mention storage.",
            nodes=[
                ArchitectureNode(
                    node_id="dashboard",
                    label="Dashboard",
                    plain_summary="Shows status.",
                    status="built",
                    evidence_refs=["src/missing.py"],
                )
            ],
        ),
    )

    report = analyze_goal_issues(snapshot)

    assert any(issue.area == "architecture" for issue in report.issues)
    assert any("src/storage.py" in issue.summary for issue in report.issues)
    assert any("src/missing.py" in issue.summary for issue in report.issues)


def test_issue_report_suggests_professional_boundary_template(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Prepare financial options for a retirement decision.",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[],
        current_phase=None,
        definition_of_done=["Done"],
    )

    report = analyze_goal_issues(snapshot)

    assert any(issue.area == "boundary" for issue in report.issues)
    assert "Professional boundary template needed for financial goal." not in report.user_questions
    assert any(
        "goals boundary explain --domain financial" in action for action in report.agent_actions
    )


def test_issue_report_includes_asset_provenance_actions(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Create launch visuals",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[],
        current_phase=None,
        definition_of_done=["Done"],
        assets=[
            AssetRecord(
                title="Launch hero",
                locator="assets/hero.png",
                asset_type="image",
                origin="external",
                usage_rights="unknown",
            )
        ],
    )

    report = analyze_goal_issues(snapshot)

    assert any(issue.area == "asset" for issue in report.issues)
    assert any("Confirm usage rights" in action for action in report.agent_actions)
