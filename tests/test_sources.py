from datetime import datetime, timezone

from goals.models import GoalSnapshot, SourceClaim, SourceRecord, WorktreeLease
from goals.runtime import default_phases
from goals.sources import (
    analyze_source_freshness,
    render_claim_summary,
    render_source_freshness_report,
    render_source_summary,
    unresolved_claims,
)


def test_source_summaries_and_unresolved_claims() -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Research customer needs",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/repo", branch="goal/demo"
        ),
        phases=default_phases("Research customer needs"),
        current_phase="P1",
        sources=[
            SourceRecord(
                source_id="SRC-1",
                title="Interview",
                source_type="interview",
                summary="Customer wants simple status.",
                credibility="high",
            )
        ],
        source_claims=[
            SourceClaim(claim="Status should be plain.", source_ids=["SRC-1"], confidence=0.8),
            SourceClaim(claim="Missing source.", source_ids=["SRC-missing"], confidence=0.2),
        ],
    )

    assert "Interview" in render_source_summary(snapshot)
    assert "Status should be plain." in render_claim_summary(snapshot)
    assert unresolved_claims(snapshot)[0].claim == "Missing source."


def test_source_freshness_flags_stale_claim_evidence() -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Research customer needs",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/repo", branch="goal/demo"
        ),
        phases=default_phases("Research customer needs"),
        current_phase="P1",
        sources=[
            SourceRecord(
                source_id="SRC-old",
                title="Old market report",
                source_type="url",
                added_at="2025-01-01T00:00:00+00:00",
            )
        ],
        source_claims=[
            SourceClaim(
                claim="Buyers want plain progress.",
                source_ids=["SRC-old"],
                confidence=0.8,
            )
        ],
    )

    report = analyze_source_freshness(
        snapshot,
        now=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )
    rendered = render_source_freshness_report(report)

    assert report.passed is False
    assert report.findings[0].severity == "p1"
    assert report.findings[0].claim_refs == ["Buyers want plain progress."]
    assert report.user_questions == []
    assert "Source Freshness Report" in rendered
    assert "Old market report" in rendered


def test_source_freshness_escalates_stale_high_stakes_claims_to_user() -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Prepare medical safety guidance",
        why="Medical and safety claims must be current.",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/repo", branch="goal/demo"
        ),
        phases=default_phases("Prepare medical safety guidance"),
        current_phase="P1",
        sources=[
            SourceRecord(
                source_id="SRC-med",
                title="Old clinical note",
                source_type="document",
                added_at="2024-01-01T00:00:00+00:00",
            )
        ],
        source_claims=[
            SourceClaim(
                claim="A safety recommendation is acceptable.",
                source_ids=["SRC-med"],
                confidence=0.9,
            )
        ],
    )

    report = analyze_source_freshness(
        snapshot,
        now=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert report.passed is False
    assert report.findings[0].needs_user is True
    assert report.user_questions == ["Source may be stale: Old clinical note"]


def test_source_freshness_flags_invalid_timestamps() -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Research customer needs",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/repo", branch="goal/demo"
        ),
        phases=default_phases("Research customer needs"),
        current_phase="P1",
        sources=[
            SourceRecord(
                source_id="SRC-bad",
                title="Broken timestamp",
                source_type="document",
                added_at="not-a-date",
            )
        ],
    )

    report = analyze_source_freshness(snapshot)

    assert report.passed is False
    assert report.findings[0].summary == "Source freshness cannot be checked: Broken timestamp"
