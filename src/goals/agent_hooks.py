"""Backends for Claude Code plugin hooks.

These produce the JSON payloads Claude Code expects, but live in the package so
they are testable in-process. The plugin's ``hooks.json`` just runs the matching
``goals hooks ...`` command, so there is no fragile standalone script and no
second code path.

- **SessionStart** → inject the context of the goal really in progress: the session's own
  folder's goal, or, when that one is finished or missing, the goal in progress in another of
  the repo's working folders (several are listed). Silent no-op if none.
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
from goals.checkpoints import build_current_checkpoint_brief, checkpoint_is_asked
from goals.git_ops import find_git_root, goal_worktrees
from goals.models import (
    Event,
    EventType,
    GateVerdict,
    GoalBrief,
    GoalSnapshot,
    GoalStatus,
    Phase,
    UserMessage,
)
from goals.portability import render_context_block
from goals.runtime import (
    MAX_PHASE_ATTEMPTS_ENV,
    active_goal_dir,
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


#: Most goals listed when several are in progress; the rest are only counted.
MAX_LISTED_GOALS = 5

#: Longest question or objective kept on one line of the session-start block.
_LINE_CHARS = 160

_NEXT_COMMAND = "goals next --agent claude"


def session_start_payload(cwd: Path) -> str:
    """JSON that injects the goal this session should work from, or "" when there is none.

    The goal in the session's own folder comes first, as it always has. When that goal is
    finished or missing, the repo's other working folders are searched for a goal that is really
    in progress: one is named (with its folder), several are listed so the user can say which.

    A hook must never crash the session, so any failure degrades to a silent no-op (fail-open)
    rather than propagating, and any failure in the new search degrades to exactly what this
    hook gave before it looked past the session's own folder.
    """
    own_dir: Path | None = None
    own: GoalSnapshot | None = None
    try:
        own_dir = active_goal_dir(cwd)
        own = load_active_snapshot(cwd)
    except Exception:  # noqa: BLE001 - no goal here, or an unreadable one: look elsewhere
        own = None
    try:
        today = render_context_block(own) if own is not None else ""
    except Exception:  # noqa: BLE001 - never crash a session hook; no-op instead
        today = ""
    try:
        text = _session_start_text(cwd, own_dir, own) or today
    except Exception:  # noqa: BLE001 - the search is an extra: fall back to today's block
        text = today
    if not text:
        return ""
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    )


def _session_start_text(cwd: Path, own_dir: Path | None, own: GoalSnapshot | None) -> str:
    """The block to inject, or "" to keep today's (own folder's goal, or nothing)."""
    if own is not None and own.status in _RECORDING_STATUSES:
        # Already in the right folder: the same block as ever, plus where things stand.
        return "\n".join([render_context_block(own), "", *_status_lines(own)])
    live = _live_goals_elsewhere(cwd, own_dir)
    if not live:
        return ""
    if len(live) > 1:
        return _several_goals_text(live)
    folder, snapshot = live[0]
    return "\n".join(
        [
            render_context_block(snapshot),
            "",
            f"Goal folder: {folder} — this session did not start there. The folder it started "
            "in has no goal in progress (its goal is finished, or it has none). Work in the "
            "goal folder, and run `goals` commands from it.",
            *_status_lines(snapshot, folder=folder),
        ]
    )


def _live_goals_elsewhere(cwd: Path, own_dir: Path | None) -> list[tuple[Path, GoalSnapshot]]:
    """Goals in progress in the repo's working folders other than the session's own goal."""
    found: list[tuple[Path, GoalSnapshot]] = []
    for tier, _own_checkout in _candidate_goal_dirs(cwd):
        for goal_dir in tier:
            if own_dir is not None and goal_dir.resolve() == own_dir.resolve():
                continue
            try:
                snapshot = EventStore(goal_dir).snapshot()
            except Exception:  # noqa: BLE001 - an unreadable log: skip that folder, keep going
                continue
            if snapshot.status in _RECORDING_STATUSES:
                found.append((goal_dir.parents[2], snapshot))
    found.sort(key=lambda item: item[1].last_updated, reverse=True)
    return found


def _status_lines(snapshot: GoalSnapshot, *, folder: Path | None = None) -> list[str]:
    """"Waiting on" and "Next" lines: the last thing in the block, so the action is the last read."""
    brief = build_goal_brief(snapshot)
    where = f" (in {folder})" if folder is not None else ""
    if brief.waiting_on == "you":
        question = _open_question(brief)
        return [f"Waiting on: you — {question}", f"Next: ask the user: {question}{where}"]
    if brief.waiting_on == "agent":
        return [
            "Waiting on: the agent (nothing needed from the user)",
            f"Next: run `{_NEXT_COMMAND}`{where}",
        ]
    return ["Waiting on: no one", f"Next: run `goals check`{where}"]


def _open_question(brief: GoalBrief) -> str:
    checkpoint = brief.current_checkpoint
    if checkpoint is not None and checkpoint.waiting_on == "you" and checkpoint.checkpoint_title:
        text = checkpoint.checkpoint_title
    elif brief.user_actions:
        text = brief.user_actions[0].plain_summary
    else:
        text = "see `goals brief`"
    return _one_line(text.removeprefix("Ask the user:").strip())


def _several_goals_text(live: list[tuple[Path, GoalSnapshot]]) -> str:
    lines = [
        "## Goals in progress in this repo",
        "",
        "The folder this session started in has no goal in progress, but these are:",
    ]
    for folder, snapshot in live[:MAX_LISTED_GOALS]:
        waiting = build_current_checkpoint_brief(snapshot).waiting_on
        lines.append(
            f"- {_one_line(snapshot.objective)} (step {snapshot.current_phase or 'none'}, "
            f"waiting on {waiting}): {folder}"
        )
    hidden = len(live) - MAX_LISTED_GOALS
    if hidden > 0:
        lines.append(f"- ...and {hidden} more not shown")
    lines += [
        "",
        "Next: if this conversation has not already settled which goal we are working on, ask "
        f"the user which one; then work in that goal's folder and run `{_NEXT_COMMAND}` there.",
    ]
    return "\n".join(lines)


def _one_line(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= _LINE_CHARS else flat[: _LINE_CHARS - 1].rstrip() + "…"


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

    - A checkpoint asked from a known host session only takes replies typed in
      that same session, so chat in another session never lands in it.
    - For checkpoints with no known session: if the session's checkout holds an
      active goal waiting on the user (in place, or the session runs inside its
      worktree), only that; from a base checkout whose goals live in worktrees,
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
    matched: list[tuple[EventStore, str]] = []
    unstamped_tiers: list[tuple[list[tuple[EventStore, str]], bool]] = []
    for goal_dirs, own in _candidate_goal_dirs(cwd):
        unstamped: list[tuple[EventStore, str]] = []
        for goal_dir in goal_dirs:
            if not _might_be_waiting(goal_dir):
                continue
            store = EventStore(goal_dir)
            try:
                snapshot = store.snapshot()
            except Exception:  # noqa: BLE001 - one unreadable goal must not stop the rest
                continue
            if snapshot.status not in _RECORDING_STATUSES:
                continue
            asked = [
                checkpoint
                for phase in snapshot.phases
                for checkpoint in phase.checkpoints
                if checkpoint_is_asked(checkpoint)
            ]
            if session_id and any(c.asked_session == session_id for c in asked):
                matched.append((store, snapshot.goal_id))
            elif any(not c.asked_session for c in asked):
                unstamped.append((store, snapshot.goal_id))
        unstamped_tiers.append((unstamped, own))
    # A session match is unambiguous wherever it is. Otherwise the nearest tier
    # with anything waiting decides: all of the session's own checkout, or a
    # lone waiting worktree goal.
    targets = matched
    if not targets:
        for unstamped, own in unstamped_tiers:
            if unstamped:
                if own or len(unstamped) == 1:
                    targets = unstamped
                break
    recorded = 0
    for store, goal_id in targets:
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


def _candidate_goal_dirs(cwd: Path) -> list[tuple[list[Path], bool]]:
    """Goal dirs this session could be answering, nearest first.

    First the session's own checkout (flagged ``True``), then the repo's goal
    worktrees — consulted only when the own checkout has nothing waiting.
    """
    root = find_git_root(cwd) or cwd.resolve()
    tiers: list[tuple[list[Path], bool]] = [(_goal_dirs_under(root), True)]
    try:
        worktrees = goal_worktrees(root)
    except Exception:  # noqa: BLE001 - not a git repo, or git unavailable
        worktrees = []
    found: list[Path] = []
    for worktree in worktrees:
        if worktree.resolve() != root.resolve():
            found.extend(_goal_dirs_under(worktree))
    tiers.append((found, False))
    return tiers


def _might_be_waiting(goal_dir: Path) -> bool:
    """Cheap pre-check on the saved snapshot before replaying a goal's whole log.

    Runs on every prompt for every goal in the repo, so finished or idle goals
    are skipped without a replay. Anything unreadable is replayed to be safe.
    """
    try:
        state = json.loads((goal_dir / "goal.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    if state.get("status") not in {status.value for status in _RECORDING_STATUSES}:
        return False
    for phase in state.get("phases", []):
        for checkpoint in phase.get("checkpoints", []):
            if checkpoint.get("status") in {"passed", "waived"}:
                continue
            if checkpoint.get("needs_user") or checkpoint.get("status") == "needs_user":
                return True
    return False


def _goal_dirs_under(root: Path) -> list[Path]:
    goals_dir = root / ".agent-workflow" / "goals"
    if not goals_dir.is_dir():
        return []
    return [child for child in sorted(goals_dir.iterdir()) if (child / "goal.json").exists()]
