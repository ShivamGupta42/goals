from pathlib import Path

from goals.architecture import (
    architecture_for_snapshot,
    render_architecture_markdown,
    render_mermaid,
)
from goals.models import Evidence, GoalSnapshot, PhaseStatus, WorktreeLease
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
    assert "Confirm outcome and plan" in text


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
