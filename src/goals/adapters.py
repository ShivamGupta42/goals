from __future__ import annotations

import subprocess
from pathlib import Path

from goals.models import GoalSnapshot


def adapter_check(name: str) -> tuple[bool, str]:
    if name == "claude":
        result = subprocess.run(
            ["claude", "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        ok = result.returncode == 0
        return ok, result.stdout.strip() or result.stderr.strip()
    if name == "codex":
        result = subprocess.run(
            ["codex", "features", "list"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        for line in result.stdout.splitlines():
            if line.startswith("goals"):
                return "true" in line.split(), line.strip()
        return False, "Codex goals feature not found."
    return False, f"Unknown adapter: {name}"


def native_goal_prompt(snapshot: GoalSnapshot, adapter: str) -> str:
    goal_file = (
        Path(snapshot.topology.worktree_path)
        / ".agent-workflow"
        / "goals"
        / snapshot.goal_id
        / "goal.json"
    )
    return (
        f"/goal Finish this Goals-managed task: {snapshot.objective}\n\n"
        f"Use Goals as the durable source of workflow state. Read `{goal_file}` before each turn. "
        "Work only on the current phase, record evidence with `goals phase evidence`, run "
        "`goals phase review`, and do not mark a phase accepted until the review gate passes. "
        f"This is a {adapter} native goal loop; Goals is the state and review layer."
    )
