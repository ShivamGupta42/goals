"""Backends for Claude Code plugin hooks.

These produce the JSON payloads Claude Code expects, but live in the package so
they are testable in-process. The plugin's ``hooks.json`` just runs the matching
``goals hooks ...`` command, so there is no fragile standalone script and no
second code path.

- **SessionStart** → inject the active goal's context (silent no-op if none).
- **Stop** (opt-in) → block stopping while the current phase still needs the
  agent, so the loop doesn't end mid-phase. Off unless ``GOALS_ENFORCE`` is set.
- **UserPromptSubmit** → record the user's own typed words in every goal that is
  waiting on them, so a user checkpoint can cite the actual reply instead of the
  agent's claim that they agreed. Silent; never blocks the prompt.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from goals.brief import build_goal_brief
from goals.checkpoints import checkpoint_is_asked
from goals.git_ops import find_git_root, goal_worktrees
from goals.models import Event, EventType, GateVerdict, GoalStatus, Phase, UserMessage
from goals.portability import render_context_block
from goals.runtime import (
    MAX_PHASE_ATTEMPTS_ENV,
    load_active_snapshot,
    resolve_max_phase_attempts,
)
from goals.storage import EventStore
from goals.token_budget import transcript_token_usage

#: Re-exported so callers/tests can reach the cap env var via agent_hooks.
MAX_ATTEMPTS_ENV = MAX_PHASE_ATTEMPTS_ENV

#: Longest user message kept verbatim; anything past it is clipped.
MAX_USER_MESSAGE_CHARS = 2000

#: Env var that turns the Stop gate on. Off by default so it never nags.
ENFORCE_ENV = "GOALS_ENFORCE"

#: Token ceiling for the enforced Stop gate. Opt-in (no default): when set, the
#: gate stops trapping the agent once the session transcript's billed tokens
#: reach this many — a deterministic budget guard in tokens, not USD. Unlike the
#: attempt cap it has no default, since any fixed number would arbitrarily cut
#: off legitimately long sessions.
MAX_TOKENS_ENV = "GOALS_MAX_TOKENS"

# Circuit breaker: how many phase-review attempts the Stop gate tolerates before
# it stops trapping the agent and hands control back to the user. Without a cap,
# an enforced Stop hook would re-block a failing review→fix→review loop forever —
# the runaway "huge AI bill" failure mode. The cap (GOALS_MAX_PHASE_ATTEMPTS) is
# resolved by goals.runtime.resolve_max_phase_attempts so the gate and this hook
# share one value and agree; MAX_ATTEMPTS_ENV is re-exported above for callers.


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


def stop_payload(
    cwd: Path, *, enforce: bool | None = None, transcript_path: str | None = None
) -> str:
    """JSON that blocks Stop while the current phase needs the agent, or "".

    Opt-in: returns "" (allow stop) unless ``enforce`` is true (defaults to the
    ``GOALS_ENFORCE`` env var). Never blocks a finished/failed/paused/blocked
    goal, nor one waiting on the user. Two circuit breakers also force a stop even
    when agent work remains: the review-attempt cap, and — when ``transcript_path``
    is supplied and ``GOALS_MAX_TOKENS`` is set — a token budget ceiling. Both
    read durable signals only, never the transcript's prose. Fail-open: any
    unexpected error allows the stop rather than trapping the agent (a Stop hook
    that errors out would otherwise be treated as a block).
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
        if _token_budget_exceeded(transcript_path):
            # The session has burned through its token budget. Re-blocking would
            # keep spending; hand control back to the user instead.
            return ""
        phase = next(
            (p for p in snapshot.phases if p.phase_id == snapshot.current_phase), None
        )
        if phase is not None and _circuit_breaker_tripped(phase):
            # The phase has burned through its review-fix attempts (or the gate
            # already returned BLOCKED). Re-blocking would just loop the same
            # failing attempt and spend without converging — hand it back to the
            # user instead. The reason for the stop is recorded on the phase's
            # gate results and surfaces via `goals check`/`goals issues`.
            return ""
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


def _circuit_breaker_tripped(phase: Phase, *, max_attempts: int | None = None) -> bool:
    """True when the Stop gate should stop trapping the agent on ``phase``.

    Deterministic — reads only durable gate history, never the transcript. The
    decision keys off the *latest* phase-review, so a stale ``BLOCKED``/``FAIL``
    from an earlier cycle can't trip the breaker after a later ``PASS``, and a
    stale ``PASS`` can't mask a newer failure. It trips when either signal fires:

    1. The latest phase-review verdict is ``BLOCKED`` — the gate's own circuit
       breaker (``goals.gates._blocked_after_cap``) already gave up on this phase.
    2. The phase has failed review at least ``max_attempts`` times, as a fallback
       for the case where reviews accumulated as ``FAIL`` without ever flipping to
       ``BLOCKED``. The gate's recorded ``attempts`` count is trusted when higher,
       so the two breakers share a cap and agree.

    A latest verdict of ``PASS`` never trips: the phase is converging, not stuck.
    """
    if max_attempts is None:
        max_attempts = resolve_max_phase_attempts()
    reviews = [r for r in phase.reviews if r.gate_id == "phase-review"]
    if not reviews:
        return False
    latest = reviews[-1]
    if latest.verdict == GateVerdict.PASS:
        return False
    if latest.verdict == GateVerdict.BLOCKED:
        return True
    if latest.verdict != GateVerdict.FAIL:
        return False
    fail_count = sum(1 for r in reviews if r.verdict == GateVerdict.FAIL)
    return max(latest.attempts, fail_count) >= max_attempts


def _token_budget_exceeded(transcript_path: str | None) -> bool:
    """True when the session transcript's billed tokens reach the ceiling.

    Deterministic — sums per-call ``usage`` from the transcript file. Returns
    False (no ceiling) when the cap is unset, no transcript was supplied, or the
    transcript can't be read, so a missing signal can never force a stop.
    """
    cap = _max_tokens()
    if cap is None or not transcript_path:
        return False
    try:
        usage = transcript_token_usage(transcript_path)
    except Exception:  # noqa: BLE001 - never let token accounting break the hook
        return False
    return usage.total >= cap


def _max_tokens() -> int | None:
    """Read the token ceiling from the environment, or None when not enforced.

    Unset means no ceiling. A non-integer or non-positive value also disables it
    rather than guessing a number — a token budget is too session-specific to
    invent a fallback for, and silently capping at a wrong value is worse than
    not capping.
    """
    raw = os.environ.get(MAX_TOKENS_ENV)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def record_user_prompt(cwd: Path, prompt: str, *, session_id: str = "") -> int:
    """UserPromptSubmit backend: record the user's words in the goal waiting on them.

    Scoped so a reply meant for one goal can't close another's checkpoint:

    - If the session's checkout holds goal state (an in-place goal, or the
      session runs inside a goal's worktree), only those goals are considered.
    - From a base checkout whose goals live in worktrees, a reply is recorded
      only when exactly one goal is waiting — with two, it's ambiguous, so none.

    Only active goals with a checkpoint put to the user record anything, and
    slash commands (``/goals:next``) are commands, not answers. Returns how many
    goals recorded it.
    """
    text = prompt.strip()
    if not text or text.startswith("/"):
        return 0
    if len(text) > MAX_USER_MESSAGE_CHARS:
        text = text[: MAX_USER_MESSAGE_CHARS - 1] + "…"
    goal_dirs, own_checkout = _candidate_goal_dirs(cwd)
    waiting: list[tuple[EventStore, str]] = []
    for goal_dir in goal_dirs:
        store = EventStore(goal_dir)
        try:
            snapshot = store.snapshot()
        except Exception:  # noqa: BLE001 - one unreadable goal must not stop the rest
            continue
        if snapshot.status not in _RECORDING_STATUSES:
            continue
        if any(
            checkpoint_is_asked(checkpoint)
            for phase in snapshot.phases
            for checkpoint in phase.checkpoints
        ):
            waiting.append((store, snapshot.goal_id))
    if not own_checkout and len(waiting) > 1:
        return 0
    recorded = 0
    for store, goal_id in waiting:
        try:
            store.append(
                Event(
                    goal_id=goal_id,
                    event_type=EventType.USER_MESSAGE_RECORDED,
                    actor="user-prompt-hook",
                    payload={
                        "message": UserMessage(text=text, session_id=session_id).model_dump()
                    },
                )
            )
        except Exception:  # noqa: BLE001 - e.g. a lock timeout: skip this goal, keep going
            continue
        recorded += 1
    return recorded


#: Goals that can still be waiting on the user (BLOCKED means waiting on them).
_RECORDING_STATUSES = (GoalStatus.ACTIVE, GoalStatus.BLOCKED)


def _candidate_goal_dirs(cwd: Path) -> tuple[list[Path], bool]:
    """Goal dirs this session could be answering, and whether they're its own checkout's."""
    root = find_git_root(cwd) or cwd.resolve()
    own = _goal_dirs_under(root)
    if own:
        return own, True
    try:
        worktrees = goal_worktrees(root)
    except Exception:  # noqa: BLE001 - not a git repo, or git unavailable
        worktrees = []
    found: list[Path] = []
    for worktree in worktrees:
        if worktree.resolve() != root.resolve():
            found.extend(_goal_dirs_under(worktree))
    return found, False


def _goal_dirs_under(root: Path) -> list[Path]:
    goals_dir = root / ".agent-workflow" / "goals"
    if not goals_dir.is_dir():
        return []
    return [child for child in sorted(goals_dir.iterdir()) if (child / "goal.json").exists()]
