from pathlib import Path

from goals.citations import analyze_citation_quality, render_citation_quality_report
from goals.models import GoalSnapshot, SourceClaim, SourceRecord, WorktreeLease
from goals.runtime import default_phases


def snapshot_with_sources(
    tmp_path: Path,
    sources: list[SourceRecord],
    claims: list[SourceClaim],
    *,
    objective: str = "Prepare customer research brief",
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
        sources=sources,
        source_claims=claims,
    )


def test_citation_quality_passes_for_traceable_claim(tmp_path: Path) -> None:
    snapshot = snapshot_with_sources(
        tmp_path,
        [
            SourceRecord(
                source_id="SRC-research",
                title="Customer interview",
                locator="interview-001",
                source_type="interview",
                summary="Customer wants clearer progress.",
                credibility="high",
            )
        ],
        [
            SourceClaim(
                claim="Customers want clearer progress updates.",
                source_ids=["SRC-research"],
                confidence=0.75,
            )
        ],
    )

    report = analyze_citation_quality(snapshot)

    assert report.passed is True
    assert report.findings == []


def test_citation_quality_finds_agent_repair_work(tmp_path: Path) -> None:
    snapshot = snapshot_with_sources(
        tmp_path,
        [
            SourceRecord(
                source_id="SRC-url",
                title="Market note",
                locator="market-note",
                source_type="url",
                credibility="medium",
            )
        ],
        [
            SourceClaim(
                claim="This always proves demand.",
                source_ids=[],
                confidence=0.4,
            ),
            SourceClaim(
                claim="Competitors need this feature.",
                source_ids=["SRC-missing"],
                confidence=0.7,
            ),
            SourceClaim(
                claim="Market notes support prioritizing this.",
                source_ids=["SRC-url"],
                confidence=0.7,
            ),
        ],
    )

    report = analyze_citation_quality(snapshot)
    rendered = render_citation_quality_report(report)

    assert report.passed is False
    assert "Claim has no citation: This always proves demand." in [
        finding.summary for finding in report.findings
    ]
    assert any("Claim confidence is low" in finding.summary for finding in report.findings)
    assert any("Claim uses absolute language" in finding.summary for finding in report.findings)
    assert any("Cited source has no summary" in finding.summary for finding in report.findings)
    assert any("URL source locator is not a URL" in finding.summary for finding in report.findings)
    assert report.user_questions == []
    assert report.agent_actions
    assert "Citation Quality Report" in rendered
    assert "Overall: needs attention" in rendered


def test_high_stakes_weak_citation_surfaces_user_question(tmp_path: Path) -> None:
    snapshot = snapshot_with_sources(
        tmp_path,
        [
            SourceRecord(
                source_id="SRC-blog",
                title="Old legal blog",
                locator="https://example.test/legal",
                source_type="url",
                summary="Informal legal commentary.",
                credibility="low",
            )
        ],
        [
            SourceClaim(
                claim="The legal conclusion is safe.",
                source_ids=["SRC-blog"],
                confidence=0.9,
            )
        ],
        objective="Prepare legal safety brief",
    )

    report = analyze_citation_quality(snapshot)

    assert report.passed is False
    assert report.user_questions == [
        "High-confidence claim relies only on low-credibility sources: The legal conclusion is safe."
    ]
    assert any(finding.needs_user for finding in report.findings)
