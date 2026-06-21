from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from goals.models import Evidence, Event, EventType, GateResult, GoalSnapshot, GoalStatus
from goals.runtime import append_event, load_active_snapshot, run_gate, transition_phase, verify_phase
from goals.storage import GoalsError
from goals.user_memory import mark_interview_prompted, render_post_goal_interview


@dataclass(frozen=True)
class PhaseVerifyReport:
    results: list[dict]

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result["passed"])

    @property
    def passed(self) -> bool:
        return self.passed_count == len(self.results)


@dataclass(frozen=True)
class PhaseAcceptReport:
    snapshot: GoalSnapshot
    interview: str = ""
    warning: str = ""


def start_phase(cwd: Path, phase_id: str) -> GoalSnapshot:
    return transition_phase(cwd, phase_id, "start")


def record_phase_evidence(cwd: Path, phase_id: str, evidence: Evidence) -> GoalSnapshot:
    snapshot = load_active_snapshot(cwd)
    return append_event(
        cwd,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": phase_id, "evidence": evidence.model_dump()},
        ),
    )


def verify_phase_workflow(cwd: Path, phase_id: str) -> PhaseVerifyReport:
    return PhaseVerifyReport(results=verify_phase(cwd, phase_id))


def review_phase_workflow(cwd: Path, phase_id: str) -> GateResult:
    return run_gate(cwd, phase_id)


def accept_phase(cwd: Path, phase_id: str) -> PhaseAcceptReport:
    snapshot = transition_phase(cwd, phase_id, "accept")
    if snapshot.status != GoalStatus.COMPLETE:
        return PhaseAcceptReport(snapshot=snapshot)
    try:
        interview = render_post_goal_interview(snapshot.goal_id) if mark_interview_prompted(snapshot.goal_id) else ""
        return PhaseAcceptReport(snapshot=snapshot, interview=interview)
    except GoalsError as exc:
        return PhaseAcceptReport(snapshot=snapshot, warning=f"User memory warning: {exc}")
