from goals.models import GoalSnapshot, SourceClaim, SourceRecord, WorktreeLease
from goals.runtime import default_phases
from goals.sources import render_claim_summary, render_source_summary, unresolved_claims


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
