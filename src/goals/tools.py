from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from goals.models import Event, EventType, ToolHealthCheck, ToolHealthReport
from goals.runtime import append_event, load_active_snapshot
from goals.storage import GoalsError


CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def analyze_tools() -> ToolHealthReport:
    checks = [
        _cli_check("claude", ["claude", "--version"], "native-agent"),
        _cli_check("codex", ["codex", "features", "list"], "native-agent"),
        _playwright_check(),
        _system_browser_check(),
    ]
    browser_ok = any(
        check.capability == "browser-render-validation"
        and check.status in {"ok", "fallback"}
        for check in checks
    )
    native_ok = any(
        check.capability == "native-agent" and check.status == "ok" for check in checks
    )
    passed = browser_ok or native_ok
    return ToolHealthReport(
        passed=passed,
        summary=(
            f"{len(checks)} tool check(s): "
            f"{sum(1 for check in checks if check.status == 'ok')} ok, "
            f"{sum(1 for check in checks if check.status == 'fallback')} fallback."
        ),
        checks=checks,
    )


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


def _cli_check(tool: str, cmd: list[str], capability: str) -> ToolHealthCheck:
    if shutil.which(cmd[0]) is None:
        return ToolHealthCheck(
            tool=tool,
            capability=capability,
            status="missing",
            detail=f"{cmd[0]} executable not found.",
        )
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolHealthCheck(
            tool=tool,
            capability=capability,
            status="unhealthy",
            detail=str(exc),
        )
    detail = (proc.stdout or proc.stderr).strip().splitlines()
    return ToolHealthCheck(
        tool=tool,
        capability=capability,
        status="ok" if proc.returncode == 0 else "unhealthy",
        detail=detail[0] if detail else f"exit={proc.returncode}",
    )


def _playwright_check() -> ToolHealthCheck:
    try:
        import playwright  # type: ignore  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return ToolHealthCheck(
            tool="playwright",
            capability="browser-render-validation",
            status="fallback" if _system_browser_path() else "missing",
            detail=f"Playwright import failed: {exc}",
            fallback="Use system Chrome/webbrowser checks." if _system_browser_path() else "",
        )
    return ToolHealthCheck(
        tool="playwright",
        capability="browser-render-validation",
        status="ok",
        detail="Playwright Python package is importable.",
    )


def _system_browser_check() -> ToolHealthCheck:
    path = _system_browser_path()
    if path:
        return ToolHealthCheck(
            tool="system-browser",
            capability="browser-render-validation",
            status="fallback",
            detail=f"Found browser at {path}.",
            fallback="Use committed Playwright/Chrome scripts when richer browser tooling is unavailable.",
        )
    return ToolHealthCheck(
        tool="system-browser",
        capability="browser-render-validation",
        status="missing",
        detail="No common Chrome/Chromium path found.",
    )


def _system_browser_path() -> str:
    for path in CHROME_PATHS:
        if Path(path).exists():
            return path
    for exe in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(exe)
        if found:
            return found
    return ""
