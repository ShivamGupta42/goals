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

DEMO_OBJECTIVE = "Create a reusable first-goal starter kit"
DEMO_WHY = (
    "Give new users a useful artifact while proving that Goals can plan, record "
    "evidence, pass review, and show proof."
)
STARTER_KIT_FILE = "FIRST_GOAL.md"


@dataclass(frozen=True)
class DemoReport:
    workspace_path: Path
    goal_id: str
    accepted_phase: str
    current_phase: str | None
    dashboard_path: Path
    starter_kit_path: Path
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
            "starter_kit_path": str(self.starter_kit_path),
            "portable_goal_path": str(self.portable_goal_path),
            "portable_state_path": str(self.portable_state_path),
            "next_commands": self.next_commands,
        }


def run_demo(out: Path | None = None) -> DemoReport:
    """Create a standalone demo goal and accept its first phase with real evidence."""
    workspace = _prepare_workspace(out)
    _write_demo_readme(workspace)
    starter_kit_path = _write_starter_kit(workspace)

    snapshot = create_goal(DEMO_OBJECTIVE, workspace, why=DEMO_WHY, workspace="in_place")
    emit_dashboard(workspace)
    export_goal(workspace)

    phase = next(phase for phase in snapshot.phases if phase.phase_id == "P1")
    evidence = Evidence(
        changed_files=["README.md", STARTER_KIT_FILE],
        checks_run=[
            "Created a standalone demo workspace with a reusable first-goal starter kit.",
            "Rendered the Goals dashboard.",
            "Exported the portable goal spec.",
        ],
        acceptance_met=[
            *phase.acceptance_criteria,
            "The starter kit gives the user a practical template for their first real goal.",
        ],
        confidence=0.95,
        notes=(
            "Goals demo produced FIRST_GOAL.md as a first-goal starter kit, then "
            "recorded evidence for the first phase so the dashboard can show "
            "proof of a useful artifact."
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
        starter_kit_path=starter_kit_path,
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
            f"Useful artifact: `{report.starter_kit_path}`",
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
        "It gives you a reusable first-goal starter kit and proves that Goals can",
        "create a plan, record evidence, pass review, accept one phase, and render",
        "a dashboard without touching another project.",
    ]
    if report is not None:
        lines += [
            "",
            "## What happened",
            "",
            "- Created a real Goals-managed goal.",
            f"- Created `{STARTER_KIT_FILE}`, a reusable starter kit for your first real goal.",
            f"- Accepted phase `{report.accepted_phase}` with recorded evidence.",
            f"- Left phase `{report.current_phase or 'none'}` as the next active phase.",
            "- Rendered the dashboard and portable goal files.",
            "",
            "## Inspect it",
            "",
            f"- Useful artifact: `{report.starter_kit_path}`",
            f"- Dashboard: {report.dashboard_uri}",
            f"- Portable goal spec: `{report.portable_goal_path}`",
            f"- Portable state JSON: `{report.portable_state_path}`",
            "",
            "## Next commands",
            "",
            *[f"{index}. `{command}`" for index, command in enumerate(report.next_commands, start=1)],
        ]
    atomic_write_text(workspace / "README.md", "\n".join(lines) + "\n")


def _write_starter_kit(workspace: Path) -> Path:
    path = workspace / STARTER_KIT_FILE
    atomic_write_text(
        path,
        "\n".join(
            [
                "# First Goal Starter Kit",
                "",
                "Use this file after the demo to turn a vague AI request into a",
                "Goals-tracked task with clear proof.",
                "",
                "## 1. Name One Concrete Outcome",
                "",
                "Start with one result someone can inspect.",
                "",
                "- Vague: `make my project better`",
                "- Clear: `add login with email/password and document how to test it`",
                "",
                "## 2. Write A Definition Of Done",
                "",
                "A good definition of done says what must be true at the end.",
                "",
                "- The requested behavior exists.",
                "- The important files or screens are named.",
                "- Tests, checks, or manual verification are recorded.",
                "- Known gaps are explicit.",
                "",
                "## 3. Decide What Evidence Counts",
                "",
                "Evidence is proof that work happened and was checked.",
                "",
                "- Automated checks, such as `pytest` or `npm test`.",
                "- Manual checks, such as opening a dashboard or trying a workflow.",
                "- Changed files, screenshots, logs, or exported artifacts.",
                "",
                "## 4. Start Your Real Goal",
                "",
                "Run this from the project you want to improve:",
                "",
                '```bash',
                'goals start "add the concrete outcome here"',
                '```',
                "",
                "Then use `goals next`, `goals check`, and `goals view --open` as the",
                "work progresses.",
                "",
            ]
        ),
    )
    return path


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
