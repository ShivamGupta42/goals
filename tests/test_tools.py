import json
from pathlib import Path

from goals.models import ToolHealthCheck, ToolHealthReport
from goals.runtime import create_goal, load_active_snapshot
from goals.tools import record_tool_health, render_tool_health_report


def test_tool_health_recording_updates_goal_state_and_portable_export(tmp_path: Path) -> None:
    create_goal("Validate browser tooling", tmp_path, workspace="in_place")
    report = ToolHealthReport(
        passed=True,
        summary="1 fallback.",
        checks=[
            ToolHealthCheck(
                tool="system-browser",
                capability="browser-render-validation",
                status="fallback",
                detail="Found a system browser.",
                fallback="Use a fallback render script.",
            )
        ],
    )

    recorded = record_tool_health(tmp_path, report)
    snapshot = load_active_snapshot(tmp_path)
    portable = json.loads((tmp_path / ".goals" / "goal-state.json").read_text())
    rendered = render_tool_health_report(recorded)

    assert recorded.recorded is True
    assert snapshot.tool_health[0].tool == "system-browser"
    assert portable["tool_health"][0]["status"] == "fallback"
    assert "Recorded tool health" in rendered
