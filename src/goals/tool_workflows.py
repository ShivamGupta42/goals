from __future__ import annotations

from pathlib import Path

from goals.models import ToolHealthReport
from goals.tools import analyze_tools, record_tool_health


def tool_doctor(cwd: Path, *, record: bool = False) -> ToolHealthReport:
    report = analyze_tools()
    return record_tool_health(cwd, report) if record else report
