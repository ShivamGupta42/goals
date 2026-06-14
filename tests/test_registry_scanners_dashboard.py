from pathlib import Path

import pytest

from goals.dashboard import render_dashboard
from goals.models import (
    ArchitectureEdge,
    ArchitectureNode,
    CheckpointStatus,
    Evidence,
    GoalArchitectureMap,
    GoalSnapshot,
    JudgementRecord,
    Phase,
    PhaseCheckpoint,
    PhaseStatus,
    WorktreeLease,
)
from goals.registry import validate_registry_file
from goals.runtime import default_phases
from goals.storage import GoalsError


def _lease(tmp_path: Path) -> WorktreeLease:
    return WorktreeLease(
        base_repo=str(tmp_path),
        base_branch="main",
        worktree_path=str(tmp_path),
        branch="goal/demo",
    )


def test_registry_rejects_unknown_critical_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text("version: 1\nkind: gates\nsurprise: true\n")
    with pytest.raises(GoalsError):
        validate_registry_file(path)


def test_dashboard_escapes_html_and_shows_overview(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="<script>alert(1)</script>",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    # XSS escaping holds.
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text

    # Accessibility scaffolding.
    assert 'class="skip-link"' in text
    assert '<main id="main"' in text
    assert '<html lang="en">' in text

    # The overview structure: steps + collapsible detail.
    assert "The steps" in text
    assert "Detail" in text
    assert "Proof &amp; evidence" in text
    assert "Architecture map" in text
    assert "Decisions" in text
    assert "Sources" in text
    assert "Technical details" in text
    assert "Goal ID:" in text
    assert "Source commit:" in text
    assert "P1 has no evidence yet." in text
    assert "No decisions recorded yet." in text

    # Skills and self-evolution memory are no longer part of the overview.
    assert "<h2>Skills</h2>" not in text
    assert "Self-Evolution Memory" not in text


def test_dashboard_renders_current_checkpoint_safely(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Plan launch",
        topology=_lease(tmp_path),
        phases=[
            Phase(
                phase_id="P1",
                title="Confirm launch",
                goal="Confirm launch risk.",
                checkpoints=[
                    PhaseCheckpoint(
                        checkpoint_id="CP-launch",
                        title="<b>Approve launch</b>",
                        status=CheckpointStatus.NEEDS_USER,
                        needs_user=True,
                        summary="Owner approval is needed.",
                        evidence_refs=["brief:P1"],
                    )
                ],
            )
        ],
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"

    render_dashboard(snapshot, output)
    text = output.read_text()

    assert "<b>Approve launch</b>" not in text
    assert "&lt;b&gt;Approve launch&lt;/b&gt;" in text
    assert "brief:P1" in text
    assert "Waiting on" in text


def test_dashboard_shows_decision_log_not_solicitation(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add sessions",
        topology=_lease(tmp_path),
        phases=[
            Phase(
                phase_id="P1",
                title="Inspect storage",
                goal="Find the storage shape",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(checks_run=["pytest"], confidence=0.8, notes="Done."),
            )
        ],
        current_phase=None,
        judgements=[
            JudgementRecord(
                question="Where should sessions live?",
                choice="Redis",
                rationale="<b>fast</b> and shared across nodes",
                decided_by="user",
                reversible=True,
            )
        ],
    )
    output = tmp_path / "dashboard.html"

    render_dashboard(snapshot, output)
    text = output.read_text()

    # The judgement log renders what was decided.
    assert "Where should sessions live?" in text
    assert "Chose: Redis" in text
    assert "user" in text

    # Judgement content is escaped.
    assert "<b>fast</b>" not in text
    assert "&lt;b&gt;fast&lt;/b&gt;" in text

    # Decision *solicitation* UI is gone from the dashboard.
    assert "Decision Brief" not in text
    assert "Recommended option" not in text
    assert "Suggested reply" not in text


def test_dashboard_renders_architecture_svg(tmp_path: Path) -> None:
    architecture = GoalArchitectureMap(
        title="Map",
        overview="How the parts connect.",
        nodes=[
            ArchitectureNode(
                node_id="gen", label="Generator", plain_summary="Builds the HTML.", status="built"
            ),
            ArchitectureNode(
                node_id="snap",
                label="<x>Snapshot</x>",
                plain_summary="Holds state.",
                status="in_progress",
            ),
        ],
        edges=[
            ArchitectureEdge(from_node="snap", to_node="gen"),
            # A self-loop must not break layout or draw a degenerate arrow.
            ArchitectureEdge(from_node="gen", to_node="gen"),
        ],
    )
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"

    render_dashboard(snapshot, output, architecture=architecture)
    text = output.read_text()

    # The diagram renders as inline SVG with a clean node and an arrow marker.
    assert "<svg viewBox" in text
    assert 'marker id="ah"' in text
    assert "Generator" in text

    # Node labels are escaped inside the SVG.
    assert "<x>Snapshot</x>" not in text
    assert "&lt;x&gt;Snapshot&lt;/x&gt;" in text
