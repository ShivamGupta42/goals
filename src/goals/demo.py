from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp

from goals.git_ops import find_git_root
from goals.models import Event, EventType, Evidence, GateVerdict
from goals.portability import export_goal
from goals.runtime import (
    append_event,
    create_goal,
    emit_dashboard,
    load_active_snapshot,
    run_gate,
    transition_phase,
)
from goals.storage import GoalsError, atomic_write_text

DEMO_OBJECTIVE = "Complete the first Goals demo"
DEMO_WHY = "Prove that Goals can plan, record evidence, pass review, and show proof."


@dataclass(frozen=True)
class DemoReport:
    workspace_path: Path
    goal_id: str
    accepted_phase: str
    current_phase: str | None
    dashboard_path: Path
    portable_goal_path: Path
    portable_state_path: Path

    @property
    def dashboard_uri(self) -> str:
        return self.dashboard_path.resolve().as_uri()

    @property
    def next_commands(self) -> list[str]:
        return [f"cd {self.workspace_path}", "goals check", "goals view --open"]

    def json_dict(self) -> dict[str, object]:
        return {
            "workspace_path": str(self.workspace_path),
            "goal_id": self.goal_id,
            "accepted_phase": self.accepted_phase,
            "current_phase": self.current_phase,
            "dashboard_path": str(self.dashboard_path),
            "dashboard_uri": self.dashboard_uri,
            "portable_goal_path": str(self.portable_goal_path),
            "portable_state_path": str(self.portable_state_path),
            "next_commands": self.next_commands,
        }


def run_demo(out: Path | None = None) -> DemoReport:
    """Create a standalone demo goal and accept its first phase with real evidence."""
    workspace = _prepare_workspace(out)
    _write_demo_readme(workspace)

    snapshot = create_goal(DEMO_OBJECTIVE, workspace, why=DEMO_WHY, workspace="in_place")
    emit_dashboard(workspace)
    export_goal(workspace)

    phase = next(phase for phase in snapshot.phases if phase.phase_id == "P1")
    evidence = Evidence(
        changed_files=["README.md"],
        checks_run=[
            "Created a standalone demo workspace.",
            "Rendered the Goals dashboard.",
            "Exported the portable goal spec.",
        ],
        acceptance_met=list(phase.acceptance_criteria),
        confidence=0.95,
        notes=(
            "Goals demo recorded evidence for the first phase so the dashboard "
            "can show proof instead of a claim."
        ),
    )
    append_event(
        workspace,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P1", "evidence": evidence.model_dump()},
        ),
    )
    gate = run_gate(workspace, "P1")
    if gate.verdict != GateVerdict.PASS:
        raise GoalsError(f"Demo phase review did not pass: {gate.verdict}: {gate.summary}")

    transition_phase(workspace, "P1", "accept")
    dashboard_path = emit_dashboard(workspace)
    export = export_goal(workspace)
    snapshot = load_active_snapshot(workspace)
    report = DemoReport(
        workspace_path=workspace,
        goal_id=snapshot.goal_id,
        accepted_phase="P1",
        current_phase=snapshot.current_phase,
        dashboard_path=dashboard_path,
        portable_goal_path=Path(export.markdown_path),
        portable_state_path=Path(export.state_path),
    )
    _write_demo_readme(workspace, report)

    return report


def render_demo_report(report: DemoReport) -> str:
    commands = report.next_commands
    return "\n".join(
        [
            "# Goals Demo Complete",
            "",
            f"Workspace: `{report.workspace_path}`",
            f"Goal: `{report.goal_id}`",
            f"Accepted phase: `{report.accepted_phase}`",
            f"Current phase: `{report.current_phase or 'none'}`",
            f"Dashboard: {report.dashboard_uri}",
            f"Portable goal spec: `{report.portable_goal_path}`",
            f"Portable state JSON: `{report.portable_state_path}`",
            "",
            "Next commands:",
            f"1. `{commands[0]}`",
            f"2. `{commands[1]}`",
            f"3. `{commands[2]}`",
        ]
    )


def _prepare_workspace(out: Path | None) -> Path:
    if out is None:
        workspace = Path(mkdtemp(prefix="goals-demo-")).resolve()
        _refuse_inside_git_repo(workspace)
        return workspace

    workspace = out.expanduser().resolve()
    if workspace.exists() and not workspace.is_dir():
        raise GoalsError(f"Demo output path must be a directory: {workspace}")
    if _has_active_goal(workspace):
        raise GoalsError(f"Demo output path already contains active Goals state: {workspace}")
    _refuse_inside_git_repo(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    if any(workspace.iterdir()):
        raise GoalsError(
            f"Demo output path must be empty or absent so no files are overwritten: {workspace}"
        )
    return workspace


def _write_demo_readme(workspace: Path, report: DemoReport | None = None) -> None:
    lines = [
        "# Goals Demo",
        "",
        "This workspace was created by `goals demo`.",
        "",
        "It proves that Goals can create a plan, record evidence, pass review,",
        "accept one phase, and render a dashboard without touching another project.",
    ]
    if report is not None:
        lines += [
            "",
            "## What happened",
            "",
            "- Created a real Goals-managed goal.",
            f"- Accepted phase `{report.accepted_phase}` with recorded evidence.",
            f"- Left phase `{report.current_phase or 'none'}` as the next active phase.",
            "- Rendered the dashboard and portable goal files.",
            "",
            "## Inspect it",
            "",
            f"- Dashboard: {report.dashboard_uri}",
            f"- Portable goal spec: `{report.portable_goal_path}`",
            f"- Portable state JSON: `{report.portable_state_path}`",
            "",
            "## Next commands",
            "",
            *[f"{index}. `{command}`" for index, command in enumerate(report.next_commands, start=1)],
        ]
    atomic_write_text(workspace / "README.md", "\n".join(lines) + "\n")


def _has_active_goal(path: Path) -> bool:
    goals_dir = path / ".agent-workflow" / "goals"
    if not goals_dir.is_dir():
        return False
    return any((child / "goal.json").exists() for child in goals_dir.iterdir() if child.is_dir())


def _refuse_inside_git_repo(path: Path) -> None:
    anchor = _nearest_existing_directory(path)
    if find_git_root(anchor) is not None:
        raise GoalsError(
            f"Demo output path is inside an existing git repo: {path}. "
            "Choose a standalone directory outside your project."
        )


def _nearest_existing_directory(path: Path) -> Path:
    current = path if path.exists() else path.parent
    while not current.exists():
        if current == current.parent:
            raise GoalsError(f"Could not find an existing parent directory for: {path}")
        current = current.parent
    if current.is_file():
        current = current.parent
    return current
