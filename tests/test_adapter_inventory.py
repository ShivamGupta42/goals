from __future__ import annotations

from dataclasses import dataclass
import subprocess

from goals.adapter_inventory import AdapterStatus, build_adapter_inventory, build_tool_health_report, check_adapter
from goals.skill_discovery import DiscoveredSkill


@dataclass(frozen=True)
class FakeCompleted:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def test_check_adapter_uses_injected_runner() -> None:
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> FakeCompleted:
        calls.append(cmd)
        return FakeCompleted(0, stdout="goals under development true\n")

    status = check_adapter("codex", runner=runner)

    assert status.ready is True
    assert status.detail == "goals feature: under development (enabled=true)"
    assert calls == [["codex", "features", "list"]]


def test_inventory_uses_injected_skills_and_runner() -> None:
    def runner(cmd: list[str]) -> FakeCompleted:
        if cmd[0] == "claude":
            return FakeCompleted(1, stderr="disabled")
        return FakeCompleted(0, stdout="goals experimental false\n")

    skill = DiscoveredSkill(
        name="demo",
        description="Demo skill",
        sources=["codex"],
        agents=["codex"],
        path="/skills/demo/SKILL.md",
    )

    inventory = build_adapter_inventory(runner=runner, skills=[skill])

    assert inventory.skills == [skill]
    assert inventory.adapter("claude").detail == "disabled"
    assert inventory.adapter("codex").detail == "goals feature: experimental (enabled=false)"
    assert any(check.tool == "codex" for check in inventory.tool_health.checks)


def test_check_adapter_handles_timeout_from_runner() -> None:
    def runner(cmd: list[str]) -> FakeCompleted:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=8)

    status = check_adapter("claude", runner=runner)

    assert status.ready is False
    assert status.detail == "Claude probe timed out after 8s."


def test_check_adapter_handles_os_error_from_runner() -> None:
    def runner(cmd: list[str]) -> FakeCompleted:
        raise OSError("permission denied")

    status = check_adapter("codex", runner=runner)

    assert status.ready is False
    assert status.detail == "permission denied"


def test_check_adapter_reports_exit_when_process_output_is_empty() -> None:
    def runner(cmd: list[str]) -> FakeCompleted:
        return FakeCompleted(17)

    status = check_adapter("codex", runner=runner)

    assert status.ready is False
    assert status.detail == "exit=17"


def test_tool_health_report_accepts_partial_adapter_map() -> None:
    report = build_tool_health_report(
        {"claude": AdapterStatus(name="claude", ready=True, detail="claude 1.2.3")}
    )

    assert report.checks[0].tool == "claude"
    assert report.checks[0].status == "ok"
    assert any(check.tool == "codex" for check in report.checks)
