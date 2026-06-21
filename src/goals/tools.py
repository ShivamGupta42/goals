from __future__ import annotations

from pathlib import Path

from goals.adapter_inventory import build_adapter_inventory
from goals.models import Event, EventType, ToolHealthReport
from goals.runtime import append_event, load_active_snapshot


def analyze_tools() -> ToolHealthReport:
    return build_adapter_inventory().tool_health


def record_tool_health(cwd: Path, report: ToolHealthReport) -> ToolHealthReport:
    snapshot = load_active_snapshot(cwd)
    append_event(
        cwd,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.TOOL_HEALTH_RECORDED,
            payload={"checks": [check.model_dump() for check in report.checks]},
        ),
    )
    return report.model_copy(update={"recorded": True})


def render_tool_health_report(report: ToolHealthReport) -> str:
    lines = [
        "# Tool Health",
        "",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        report.summary,
        "",
        "## Checks",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status}] {check.tool} ({check.capability}): {check.detail}")
        if check.fallback:
            lines.append(f"  Fallback: {check.fallback}")
    if report.recorded:
        lines.extend(["", "Recorded tool health in the active goal."])
    return "\n".join(lines) + "\n"
