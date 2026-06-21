from pathlib import Path

from goals.issues import AnalyzerResults, analyze_goal_issues
from goals.models import (
    ArchitectureCheckReport,
    CapabilityCheckReport,
    GoalSnapshot,
    MergeReadinessReport,
    Phase,
    SourceFreshnessReport,
    WorktreeLease,
)


def _snapshot(tmp_path: Path) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Improve health locality",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[Phase(phase_id="P1", title="Build", goal="Build", acceptance_criteria=["Done"])],
        current_phase="P1",
    )


def test_goal_issues_reuses_supplied_analyzer_results(tmp_path: Path, monkeypatch) -> None:
    def fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("analyzer should not be recomputed")

    monkeypatch.setattr("goals.issues.analyze_capabilities", fail)
    monkeypatch.setattr("goals.issues.analyze_code_architecture", fail)
    monkeypatch.setattr("goals.issues.analyze_merge_readiness", fail)
    monkeypatch.setattr("goals.issues.analyze_source_freshness", fail)

    snapshot = _snapshot(tmp_path)
    results = AnalyzerResults(
        capability=CapabilityCheckReport(goal_id="demo", passed=True, summary="ok"),
        architecture=ArchitectureCheckReport(goal_id="demo", passed=True, summary="ok"),
        merge=MergeReadinessReport(goal_id="demo", passed=True, summary="ok"),
        source_freshness=SourceFreshnessReport(goal_id="demo", passed=True, summary="ok"),
    )

    report = analyze_goal_issues(snapshot, analyzer_results=results)

    assert report.goal_id == "demo"
    assert any(issue.area == "evidence" for issue in report.issues)
