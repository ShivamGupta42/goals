"""DISCOVERY.md — Discovery's record as a plain file, generated from the event log.

Written next to the goal's dashboard (``.agent-workflow/goals/<goal>/``, kept out
of git) whenever the goal changes, once Discovery has recorded a pain point or a
desired property. Goals that predate typed Discovery records keep any
hand-written file untouched.
"""

from __future__ import annotations

from goals.checkpoint_workflows import confirmation_lines, property_state
from goals.models import GoalSnapshot
from goals.storage import atomic_write_text

FILENAME = "DISCOVERY.md"


def has_discovery_record(snapshot: GoalSnapshot) -> bool:
    return bool(snapshot.pain_points or snapshot.desired_properties)


def render_discovery_markdown(snapshot: GoalSnapshot) -> str:
    first_phase = snapshot.phases[0].phase_id if snapshot.phases else None
    pains = [p.statement for p in snapshot.pain_points if p.status == "active"]
    wants = [
        f"{w.statement} — {property_state(snapshot, w)}"
        for w in snapshot.desired_properties
        if w.status == "active"
    ]
    questions = list(
        dict.fromkeys(
            question
            for breakdown in snapshot.breakdowns
            for sub in breakdown.subproblems
            for question in sub.open_questions
        )
    )
    approach = [
        f"{j.question} → {j.choice} "
        f"({'recommended by the agent' if j.decided_by == 'agent' else 'chosen by you'})"
        + (f": {j.rationale}" if j.rationale else "")
        for j in snapshot.judgements
        if j.phase_id == first_phase
    ]
    lines = [
        f"# Discovery — {snapshot.objective}",
        "",
        "_Written by Goals from this goal's record; edits here are overwritten. Change it "
        "with `goals assess pain`, `goals assess want`, `goals assess breakdown`, and "
        "`goals decision record`._",
        "",
        "## What hurts today",
        *_bullets(pains),
        "",
        "## What good feels like",
        *_bullets(wants),
        "",
        "## What I don't understand yet",
        *_bullets(questions),
        "",
        "## How we'll approach it",
        *_bullets(approach),
        "",
        "## What the user confirmed",
        *_bullets(confirmation_lines(snapshot)),
    ]
    return "\n".join(lines) + "\n"


def refresh_discovery_notes(snapshot: GoalSnapshot) -> None:
    if not has_discovery_record(snapshot):
        return
    from goals.projections import goal_dir_for_snapshot

    atomic_write_text(goal_dir_for_snapshot(snapshot) / FILENAME, render_discovery_markdown(snapshot))


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- (nothing yet)"]
