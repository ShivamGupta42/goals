from __future__ import annotations

import subprocess

from goals.models import GoalSnapshot


def adapter_check(name: str) -> tuple[bool, str]:
    if name == "claude":
        try:
            result = subprocess.run(
                ["claude", "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            return False, "Claude executable not found."
        ok = result.returncode == 0
        return ok, result.stdout.strip() or result.stderr.strip()
    if name == "codex":
        try:
            result = subprocess.run(
                ["codex", "features", "list"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return False, "Codex executable not found."
        if result.returncode != 0:
            return False, result.stderr.strip()
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == "goals":
                enabled = parts[-1].lower() == "true"
                state = " ".join(parts[1:-1]) or "unknown"
                return enabled, f"Codex goals feature: {state} (enabled={'true' if enabled else 'false'})"
        return False, "Codex goals feature not found."
    return False, f"Unknown adapter: {name}"


def native_goal_prompt(snapshot: GoalSnapshot, adapter: str) -> str:
    from goals.mode_a import build_mode_a_plan

    selected = adapter if adapter in {"auto", "claude", "codex"} else "auto"
    return build_mode_a_plan(snapshot, selected).prompt
