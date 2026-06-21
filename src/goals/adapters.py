from __future__ import annotations

import subprocess

from goals.adapter_inventory import check_adapter
from goals.models import GoalSnapshot


def adapter_check(name: str) -> tuple[bool, str]:
    status = check_adapter(name, runner=_run_adapter_command)
    return status.ready, status.detail


def _run_adapter_command(cmd: list[str]):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def native_goal_prompt(snapshot: GoalSnapshot, adapter: str) -> str:
    from goals.mode_a import build_mode_a_plan

    selected = adapter if adapter in {"auto", "claude", "codex"} else "auto"
    return build_mode_a_plan(snapshot, selected).prompt
