from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoalStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    FAILED = "failed"
    PAUSED = "paused"


class PhaseStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"


class GateVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NEEDS_HUMAN = "needs_human"
    UNSAFE = "unsafe"


class EventType(StrEnum):
    GOAL_CREATED = "goal_created"
    PHASE_STARTED = "phase_started"
    PHASE_EVIDENCE = "phase_evidence"
    PHASE_REVIEWED = "phase_reviewed"
    PHASE_ACCEPTED = "phase_accepted"
    DECISION_REQUESTED = "decision_requested"
    LEARNING_CAPTURED = "learning_captured"
    SCAN_COMPLETED = "scan_completed"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: int = SCHEMA_VERSION
    goal_id: str
    event_type: EventType
    timestamp: str = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class Phase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_id: str
    title: str
    goal: str
    status: PhaseStatus = PhaseStatus.PENDING
    acceptance_criteria: list[str] = Field(default_factory=list)
    evidence: "Evidence | None" = None
    reviews: list["GateResult"] = Field(default_factory=list)


class WorktreeLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["single", "parallel", "swarm", "rewrite"] = "single"
    base_repo: str
    base_branch: str
    worktree_path: str
    branch: str
    created_at: str = Field(default_factory=utc_now)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changed_files: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    acceptance_met: list[str] = Field(default_factory=list)
    acceptance_not_met: list[str] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str
    verdict: GateVerdict
    summary: str
    p0: list[str] = Field(default_factory=list)
    p1: list[str] = Field(default_factory=list)
    p2: list[str] = Field(default_factory=list)
    attempts: int = 1
    created_at: str = Field(default_factory=utc_now)


class DecisionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    explanation: str
    tradeoffs: list[str] = Field(default_factory=list)
    reversible: bool = False
    reversal_plan: str = ""
    risk: Literal["low", "medium", "high"] = "medium"


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: f"D-{uuid4().hex[:8]}")
    title: str
    plain_summary: str
    why_it_matters: str
    recommendation: str
    options: list[DecisionOption]
    confidence: float = 0.0
    priority: Literal["blocking", "important", "later"] = "important"
    suggested_reply: str = ""
    technical_details: str = ""


class ScanResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanner: str
    verdict: GateVerdict
    findings: list[str] = Field(default_factory=list)


class ModeAPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: Literal["claude", "codex"]
    adapter_ready: bool = False
    adapter_detail: str = ""
    goal_file: str
    dashboard_file: str
    current_phase: str
    phase_title: str
    phase_goal: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    evidence_file: str
    evidence_template: Evidence
    prompt: str


class GoalSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    goal_id: str
    objective: str
    why: str = ""
    definition_of_done: list[str] = Field(default_factory=list)
    status: GoalStatus = GoalStatus.ACTIVE
    autonomy: Literal["careful", "standard", "fast", "swarm"] = "standard"
    topology: WorktreeLease
    phases: list[Phase]
    current_phase: str | None = None
    decisions: list[Decision] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    learnings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    last_updated: str = Field(default_factory=utc_now)
    event_count: int = 0


Phase.model_rebuild()
