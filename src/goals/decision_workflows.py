from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from goals.decisions import (
    build_decision_brief,
    build_decision_context,
    render_decision_explanation,
)
from goals.models import (
    Decision,
    DecisionBrief,
    DecisionExplanation,
    Event,
    EventType,
    JudgementRecord,
    PersonalizationContext,
)
from goals.runtime import append_event, load_active_snapshot
from goals.storage import GoalsError
from goals.user_memory import infer_area, record_observation


@dataclass(frozen=True)
class DecisionRecordReport:
    record: JudgementRecord
    warning: str = ""


def explain_decision_workflow(
    cwd: Path,
    decision: Decision,
    *,
    level: Literal["basic", "detailed", "technical"] = "basic",
    personalization: PersonalizationContext | None = None,
) -> DecisionExplanation:
    snapshot = load_active_snapshot(cwd)
    context = build_decision_context(snapshot, personalization)
    if not decision.suggested_reply:
        decision.suggested_reply = f"I choose: {decision.recommendation}"
    decision.what_we_know = decision.what_we_know or []
    decision.evidence_refs = decision.evidence_refs or []
    decision.uncertainty = decision.uncertainty or []
    return render_decision_explanation(decision, context, level=level)


def record_decision(
    cwd: Path,
    *,
    question: str,
    choice: str,
    why: str = "",
    decided_by: Literal["user", "agent"] = "user",
    reversible: bool = True,
    phase_id: str | None = None,
    evidence_refs: list[str] | None = None,
    profile_claim_ids: list[str] | None = None,
    confidence: float = 0.0,
) -> DecisionRecordReport:
    snapshot = load_active_snapshot(cwd)
    record = JudgementRecord(
        question=question,
        choice=choice,
        rationale=why,
        decided_by=decided_by,
        reversible=reversible,
        phase_id=phase_id,
        evidence_refs=evidence_refs or [],
        profile_claim_ids=profile_claim_ids or [],
        confidence=confidence,
    )
    append_event(
        cwd,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.DECISION_RECORDED,
            payload={"judgement": record.model_dump()},
        ),
    )
    warning = _record_user_judgement_signal(snapshot.goal_id, record)
    return DecisionRecordReport(record=record, warning=warning)


def decision_brief_workflow(
    cwd: Path,
    personalization: PersonalizationContext | None = None,
) -> DecisionBrief:
    return build_decision_brief(load_active_snapshot(cwd), personalization)


def _record_user_judgement_signal(goal_id: str, record: JudgementRecord) -> str:
    """Log the user's decision as a situated observation — context, not cause.

    We store *what* was decided and the observable context (the question). We do
    NOT infer or fabricate a reason; the ``--why`` note is recorded only when the
    user actually supplies one, in their own words. The observation is scoped to
    this goal and never becomes a standing preference on its own.
    """
    if record.decided_by != "user":
        return ""
    try:
        record_observation(
            goal_id=goal_id,
            # Infer the area from the question instead of a meaningless constant,
            # and carry reversibility/phase so memory can learn how this user
            # decides about risky/irreversible things (not just what they picked).
            area=infer_area(record.question),
            choice=record.choice,
            context=record.question,
            note=record.rationale,
            reversible=record.reversible,
            phase_id=record.phase_id or "",
        )
    except GoalsError as exc:
        return f"User memory warning: {exc}"
    return ""
