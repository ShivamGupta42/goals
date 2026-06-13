from pathlib import Path

from goals.architecture import (
    architecture_for_snapshot,
    build_architecture_brief,
    render_architecture_markdown,
    render_architecture_brief,
    render_mermaid,
)
from goals.models import (
    ArchitectureNode,
    Evidence,
    GoalArchitectureMap,
    GoalSnapshot,
    PhaseStatus,
    WorktreeLease,
)
from goals.runtime import default_phases


def test_architecture_defaults_to_phase_map(tmp_path: Path) -> None:
    phases = default_phases("Ship a dashboard")
    phases[0].evidence = Evidence(
        changed_files=["src/goals/dashboard.py"],
        checks_run=["uv run pytest -q"],
        acceptance_met=["dashboard renders"],
        confidence=0.9,
        notes="Dashboard updated.",
    )
    phases[0].status = PhaseStatus.ACCEPTED
    phases[1].status = PhaseStatus.IN_PROGRESS
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Ship a dashboard",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=phases,
        current_phase="P2",
    )

    architecture = architecture_for_snapshot(snapshot)
    output = tmp_path / "architecture.md"
    render_architecture_markdown(architecture, output)
    text = output.read_text()

    assert architecture.nodes[0].status == "built"
    assert "src/goals/dashboard.py" in architecture.nodes[0].evidence_refs
    assert "```mermaid" in text
    assert "Architecture Brief" in text
    assert "Verify evidence" in text
    assert "Confirm outcome and plan" in text


def test_architecture_brief_surfaces_review_focus_and_evidence_gaps() -> None:
    architecture = GoalArchitectureMap(
        title="Demo architecture",
        overview="A dashboard backed by event state.",
        nodes=[
            ArchitectureNode(
                node_id="state",
                label="Goal state",
                plain_summary="Stores events.",
                status="built",
                evidence_refs=["events.jsonl", "pytest"],
            ),
            ArchitectureNode(
                node_id="dashboard",
                label="Dashboard",
                plain_summary="Shows progress.",
                status="built",
            ),
            ArchitectureNode(
                node_id="merge",
                label="Merge gate",
                plain_summary="Checks work before merge.",
                status="blocked",
            ),
        ],
        questions=["Does the merge gate cover migrations?"],
    )

    brief = build_architecture_brief(architecture)
    rendered = render_architecture_brief(brief)

    assert brief.status_counts == {"built": 2, "blocked": 1}
    assert len(brief.evidence_gaps) == 2
    assert "2/3 architecture node(s) are built; 1 blocked." in brief.summary
    assert "Resolve or explicitly defer blocked architecture node(s): Merge gate." in rendered
    assert "Dashboard: Built node has no evidence references" in rendered
    assert "Does the merge gate cover migrations?" in rendered


def test_mermaid_sanitizes_node_ids_and_labels() -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective='Ship "quoted" view',
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/repo", branch="goal/demo"
        ),
        phases=default_phases('Ship "quoted" view'),
        current_phase="P1",
    )

    diagram = render_mermaid(architecture_for_snapshot(snapshot))

    assert 'n_P1["Confirm outcome and plan' in diagram
    assert '"quoted"' not in diagram
