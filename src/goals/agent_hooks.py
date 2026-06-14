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

#: Env var that turns the Stop gate on. Off by default so it never nags.
ENFORCE_ENV = "GOALS_ENFORCE"


# A goal in one of these states is not the agent's to push on: finished, failed,
# user-paused, or blocked (which means waiting on the user). The Stop gate exempts
# them so it never traps the agent on a goal it shouldn't be advancing.
_NON_BLOCKING_STATUSES = (
    GoalStatus.COMPLETE,
    GoalStatus.FAILED,
    GoalStatus.PAUSED,
    GoalStatus.BLOCKED,
)


def session_start_payload(cwd: Path) -> str:
    """JSON that injects the active goal block, or "" when there's no goal.

    A hook must never crash the session, so any failure degrades to a silent
    no-op (fail-open) rather than propagating.
    """
    try:
        snapshot = load_active_snapshot(cwd)
        return json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": render_context_block(snapshot),
                }
            }
        )
    except Exception:  # noqa: BLE001 - never crash a session hook; no-op instead
        return ""


def stop_payload(cwd: Path, *, enforce: bool | None = None) -> str:
    """JSON that blocks Stop while the current phase needs the agent, or "".

    Opt-in: returns "" (allow stop) unless ``enforce`` is true (defaults to the
    ``GOALS_ENFORCE`` env var). Never blocks a finished/failed/paused/blocked
    goal, nor one waiting on the user. Fail-open: any unexpected error allows the
    stop rather than trapping the agent (a Stop hook that errors out would
    otherwise be treated as a block).
    """
    if enforce is None:
        enforce = bool(os.environ.get(ENFORCE_ENV))
    if not enforce:
        return ""
    try:
        snapshot = load_active_snapshot(cwd)
        if snapshot.status in _NON_BLOCKING_STATUSES:
            return ""
        brief = build_goal_brief(snapshot)
        if brief.waiting_on != "agent":
            return ""  # waiting on the user (or no one) — don't block
        phase = next(
            (p for p in snapshot.phases if p.phase_id == snapshot.current_phase), None
        )
        where = f"{phase.phase_id} ({phase.title})" if phase else "the current phase"
        return json.dumps(
            {
                "decision": "block",
                "reason": (
                    f"Goal '{snapshot.objective}' still has agent work on {where}. "
                    "Run `goals check`, record evidence, and accept the phase before "
                    "stopping."
                ),
            }
        )
    except Exception:  # noqa: BLE001 - fail open: allow stop rather than trap the agent
        return ""
