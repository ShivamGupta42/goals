from pathlib import Path

from goals.boundaries import (
    build_professional_boundary_report,
    detect_professional_domains,
    render_professional_boundary_report,
)
from goals.models import GoalSnapshot, WorktreeLease
from goals.runtime import default_phases


def test_boundary_detection_and_basic_rendering(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Compare treatment questions after a medical diagnosis.",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Compare treatment questions"),
        current_phase="P1",
    )

    report = build_professional_boundary_report(snapshot)
    rendered = render_professional_boundary_report(report)

    assert report.domain == "medical"
    assert report.detected_domains == ["medical"]
    assert "cannot diagnose" in report.plain_boundary
    assert "Professional Boundary" in rendered
    assert "What Needs You Or A Professional" in rendered
    assert "qualified clinician" in rendered


def test_boundary_can_render_technical_financial_template() -> None:
    report = build_professional_boundary_report(domain="financial")
    rendered = render_professional_boundary_report(report, level="technical")

    assert report.domain == "financial"
    assert "Detected domains: none" in rendered
    assert "Evidence Contract" in rendered
    assert "money or long-term obligations" in rendered


def test_detect_professional_domains_prioritizes_multiple_domains() -> None:
    domains = detect_professional_domains("Legal compliance and medical safety plan")

    assert domains == ["medical", "legal", "safety"]
