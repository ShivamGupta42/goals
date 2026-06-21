from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
import shutil
import subprocess

from goals.models import ToolHealthCheck, ToolHealthReport
from goals.skill_discovery import DiscoveredSkill, discover_skills


CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str]], CommandResult]


@dataclass(frozen=True)
class AdapterStatus:
    name: str
    ready: bool
    detail: str


@dataclass(frozen=True)
class NativeAdapterInventory:
    adapters: dict[str, AdapterStatus]
    skills: list[DiscoveredSkill]
    tool_health: ToolHealthReport

    def adapter(self, name: str) -> AdapterStatus:
        return self.adapters.get(name, AdapterStatus(name=name, ready=False, detail=f"Unknown adapter: {name}"))


def build_adapter_inventory(
    *,
    runner: CommandRunner | None = None,
    skills: list[DiscoveredSkill] | None = None,
) -> NativeAdapterInventory:
    runner = runner or _run_command
    statuses = {
        name: check_adapter(name, runner=runner)
        for name in ("claude", "codex")
    }
    tool_health = build_tool_health_report(statuses)
    return NativeAdapterInventory(
        adapters=statuses,
        skills=skills if skills is not None else discover_skills(),
        tool_health=tool_health,
    )


def check_adapter(name: str, *, runner: CommandRunner | None = None) -> AdapterStatus:
    runner = runner or _run_command
    if name == "claude":
        try:
            result = runner(["claude", "--version"])
        except FileNotFoundError:
            return AdapterStatus(name, False, "Claude executable not found.")
        except subprocess.TimeoutExpired as exc:
            return AdapterStatus(name, False, _timeout_detail("Claude", exc))
        except OSError as exc:
            return AdapterStatus(name, False, _exception_detail(exc))
        ok = result.returncode == 0
        return AdapterStatus(name, ok, _result_detail(result))
    if name == "codex":
        try:
            result = runner(["codex", "features", "list"])
        except FileNotFoundError:
            return AdapterStatus(name, False, "Codex executable not found.")
        except subprocess.TimeoutExpired as exc:
            return AdapterStatus(name, False, _timeout_detail("Codex", exc))
        except OSError as exc:
            return AdapterStatus(name, False, _exception_detail(exc))
        if result.returncode != 0:
            return AdapterStatus(name, False, _result_detail(result))
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == "goals":
                enabled = parts[-1].lower() == "true"
                state = " ".join(parts[1:-1]) or "unknown"
                return AdapterStatus(
                    name,
                    enabled,
                    f"goals feature: {state} (enabled={'true' if enabled else 'false'})",
                )
        return AdapterStatus(name, False, "Codex goals feature not found.")
    return AdapterStatus(name, False, f"Unknown adapter: {name}")


def build_tool_health_report(
    adapters: dict[str, AdapterStatus] | None = None,
) -> ToolHealthReport:
    adapters = adapters or {}
    claude = adapters.get("claude") or check_adapter("claude")
    codex = adapters.get("codex") or check_adapter("codex")
    checks = [
        _adapter_tool_check(claude),
        _adapter_tool_check(codex),
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
    return ToolHealthReport(
        passed=browser_ok or native_ok,
        summary=(
            f"{len(checks)} tool check(s): "
            f"{sum(1 for check in checks if check.status == 'ok')} ok, "
            f"{sum(1 for check in checks if check.status == 'fallback')} fallback."
        ),
        checks=checks,
    )


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)


def _timeout_detail(label: str, exc: subprocess.TimeoutExpired) -> str:
    timeout = f" after {exc.timeout:g}s" if isinstance(exc.timeout, int | float) else ""
    return f"{label} probe timed out{timeout}."


def _exception_detail(exc: OSError) -> str:
    return str(exc) or exc.__class__.__name__


def _result_detail(result: CommandResult) -> str:
    return result.stdout.strip() or result.stderr.strip() or f"exit={result.returncode}"


def _adapter_tool_check(status: AdapterStatus) -> ToolHealthCheck:
    missing = "executable not found" in status.detail.lower()
    return ToolHealthCheck(
        tool=status.name,
        capability="native-agent",
        status="ok" if status.ready else "missing" if missing else "unhealthy",
        detail=status.detail,
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
