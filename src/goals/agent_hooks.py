"""Backends for Claude Code plugin hooks.

These produce the JSON payloads Claude Code expects, but live in the package so
they are testable in-process. The plugin's ``hooks.json`` just runs the matching
``goals hooks ...`` command, so there is no fragile standalone script and no
second code path.

- **SessionStart** → inject the active goal's context (silent no-op if none).
- **Stop** (opt-in) → block stopping while the current phase still needs the
  agent, so the loop doesn't end mid-phase. Off unless ``GOALS_ENFORCE`` is set.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from goals.brief import build_goal_brief
from goals.models import GoalStatus
from goals.portability import render_context_block
from goals.runtime import load_active_snapshot
from goals.storage import GoalsError

#: Env var that turns the Stop gate on. Off by default so it never nags.
ENFORCE_ENV = "GOALS_ENFORCE"


def session_start_payload(cwd: Path) -> str:
    """JSON that injects the active goal block, or "" when there's no goal."""
    try:
        snapshot = load_active_snapshot(cwd)
    except GoalsError:
        return ""
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": render_context_block(snapshot),
            }
        }
    )


def stop_payload(cwd: Path, *, enforce: bool | None = None) -> str:
    """JSON that blocks Stop while the current phase needs the agent, or "".

    Opt-in: returns "" (allow stop) unless ``enforce`` is true (defaults to the
    ``GOALS_ENFORCE`` env var). Never blocks when the goal is finished or when it
    is waiting on the user — only when there is agent work left to do.
    """
    if enforce is None:
        enforce = bool(os.environ.get(ENFORCE_ENV))
    if not enforce:
        return ""
    try:
        snapshot = load_active_snapshot(cwd)
    except GoalsError:
        return ""
    if snapshot.status in (GoalStatus.COMPLETE, GoalStatus.FAILED):
        return ""
    brief = build_goal_brief(snapshot)
    if brief.waiting_on != "agent":
        return ""  # waiting on the user (or no one) — don't block
    return json.dumps(
        {
            "decision": "block",
            "reason": (
                f"Goal '{snapshot.objective}' still has agent work on "
                f"{snapshot.current_phase}: {brief.current_step}. "
                "Run `goals check`, record evidence, and accept the phase before stopping."
            ),
        }
    )
