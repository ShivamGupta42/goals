from __future__ import annotations

from pathlib import Path

from goals.architecture import architecture_for_snapshot, render_architecture_markdown
from goals.dashboard import render_dashboard
from goals.health import GoalHealthReport, build_goal_health
from goals.models import GoalSnapshot, PortableExport
from goals.portability import export_snapshot
from goals.storage import EventStore


def goal_dir_for_snapshot(snapshot: GoalSnapshot) -> Path:
    return Path(snapshot.topology.worktree_path) / ".agent-workflow" / "goals" / snapshot.goal_id


def refresh_portable_export(snapshot: GoalSnapshot) -> PortableExport:
    return export_snapshot(snapshot)


def export_goal(cwd: Path) -> PortableExport:
    from goals.runtime import load_active_snapshot

    return refresh_portable_export(load_active_snapshot(cwd))


def emit_architecture(cwd: Path) -> Path:
    from goals.runtime import load_active_snapshot

    return emit_architecture_for_snapshot(load_active_snapshot(cwd))


def emit_architecture_for_snapshot(snapshot: GoalSnapshot) -> Path:
    architecture_path = goal_dir_for_snapshot(snapshot) / "architecture.md"
    render_architecture_markdown(architecture_for_snapshot(snapshot), architecture_path)
    return architecture_path


def emit_dashboard(cwd: Path, *, health: GoalHealthReport | None = None) -> Path:
    from goals.runtime import load_active_snapshot

    snapshot = health.snapshot if health is not None else load_active_snapshot(cwd)
    return emit_dashboard_for_snapshot(snapshot, health=health)


def emit_dashboard_for_snapshot(
    snapshot: GoalSnapshot,
    *,
    health: GoalHealthReport | None = None,
    architecture_path: Path | None = None,
) -> Path:
    goal_dir = goal_dir_for_snapshot(snapshot)
    events = EventStore(goal_dir).read_events()
    output_path = goal_dir / "dashboard.html"
    architecture_path = architecture_path or emit_architecture_for_snapshot(snapshot)
    health = health or build_goal_health(snapshot, Path(snapshot.topology.worktree_path))
    render_dashboard(
        snapshot,
        output_path,
        architecture_path=architecture_path,
        events=events,
        health=health,
    )
    return output_path


def refresh_goal_outputs(cwd: Path) -> tuple[PortableExport, Path, Path]:
    from goals.runtime import load_active_snapshot

    snapshot = load_active_snapshot(cwd)
    portable = refresh_portable_export(snapshot)
    architecture_path = emit_architecture_for_snapshot(snapshot)
    health = build_goal_health(snapshot, Path(snapshot.topology.worktree_path))
    dashboard_path = emit_dashboard_for_snapshot(
        snapshot,
        health=health,
        architecture_path=architecture_path,
    )
    return portable, architecture_path, dashboard_path
