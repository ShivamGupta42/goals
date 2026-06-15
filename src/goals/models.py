from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

# v2 dropped the asset/creative/external-review/handoff event types and the
# matching GoalSnapshot fields. Loading tolerates v1 state (storage skips
# retired events and drops unknown snapshot fields), so this bump is a signal,
# not a hard gate.
SCHEMA_VERSION = 2

# Version of the portable, vendor-neutral goal-state spec written to `.goals/`.
# Bumped independently of the internal SCHEMA_VERSION because this is the
# external contract other agents (Claude Code, Codex, Cursor, ...) read.
PORTABLE_SPEC_VERSION = 1


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
    PHASE_CHECKPOINT_RECORDED = "phase_checkpoint_recorded"
    DECISION_REQUESTED = "decision_requested"
    DECISION_RECORDED = "decision_recorded"
    ASSUMPTION_RECORDED = "assumption_recorded"
    BREAKDOWN_RECORDED = "breakdown_recorded"
    ARCHITECTURE_UPDATED = "architecture_updated"
    SOURCE_RECORDED = "source_recorded"
    LEARNING_CAPTURED = "learning_captured"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: int = SCHEMA_VERSION
    goal_id: str
    event_type: EventType
    timestamp: str = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class CheckpointKind(StrEnum):
    EVIDENCE = "evidence"
    HUMAN_VALIDATION = "human_validation"
    APPROVAL = "approval"
    EXTERNAL_REVIEW = "external_review"
    UNDERSTANDING = "understanding"
    HANDOFF = "handoff"
    CUSTOM = "custom"


class CheckpointStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    BLOCKED = "blocked"
    NEEDS_USER = "needs_user"
    WAIVED = "waived"


class PhaseCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str
    kind: CheckpointKind = CheckpointKind.CUSTOM
    title: str
    status: CheckpointStatus = CheckpointStatus.PENDING
    required: bool = True
    needs_user: bool = False
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    decision_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    notes: str = ""


class Phase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_id: str
    title: str
    goal: str
    status: PhaseStatus = PhaseStatus.PENDING
    acceptance_criteria: list[str] = Field(default_factory=list)
    evidence: "Evidence | None" = None
    reviews: list["GateResult"] = Field(default_factory=list)
    checkpoints: list[PhaseCheckpoint] = Field(default_factory=list)


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
    source_ids: list[str] = Field(default_factory=list)
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
    what_we_know: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class DecisionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_objective: str
    goal_status: str
    current_phase: str | None = None
    accepted_phases: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)
    prior_decisions: list[str] = Field(default_factory=list)
    source_claims: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    learnings: list[str] = Field(default_factory=list)
    personalization: "PersonalizationContext | None" = None


class DecisionExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["basic", "detailed", "technical"]
    surfaced_to_user: bool
    reason_for_surface: str
    markdown: str
    decision: Decision
    context: DecisionContext


class DecisionBriefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    title: str
    plain_summary: str
    why_user_needed: str
    recommendation: str
    suggested_reply: str
    confidence: float = 0.0
    highest_risk: Literal["low", "medium", "high"] = "medium"
    all_options_reversible: bool = False
    option_summaries: list[str] = Field(default_factory=list)
    what_happens_next: str
    known_context: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class DecisionBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    waiting_on_user: bool
    summary: str
    user_decisions: list[DecisionBriefItem] = Field(default_factory=list)
    agent_handled_count: int = 0
    agent_handled_summary: str = ""


class GoalBriefAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    plain_summary: str
    why_it_matters: str = ""
    suggested_reply: str = ""
    what_happens_next: str = ""
    priority: Literal["blocking", "important", "later"] = "important"
    source: Literal["checkpoint", "decision", "issue", "merge", "proof", "state"] = "issue"
    evidence_refs: list[str] = Field(default_factory=list)


class CurrentCheckpointBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    phase_id: str
    phase_title: str
    checkpoint_id: str = ""
    checkpoint_title: str = ""
    status: str
    waiting_on: Literal["you", "agent", "no one"]
    why_it_matters: str
    what_changed: str
    proof: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    next_safe_step: str
    evidence_refs: list[str] = Field(default_factory=list)
    decision_refs: list[str] = Field(default_factory=list)


class GoalBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    objective: str
    status: str
    current_step: str
    waiting_on: Literal["you", "agent", "no one"]
    summary: str
    progress: str
    proof: str
    current_checkpoint: CurrentCheckpointBrief | None = None
    user_actions: list[GoalBriefAction] = Field(default_factory=list)
    agent_actions: list[GoalBriefAction] = Field(default_factory=list)
    technical_details: list[str] = Field(default_factory=list)


class PermissionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    label: str
    description: str
    match: list[str] = Field(default_factory=list)
    decision: Literal["allow", "agent_decide", "ask_user", "deny"] = "agent_decide"
    risk: Literal["low", "medium", "high"] = "low"
    user_question: str = ""
    agent_action: str = ""


class PermissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_kind: Literal["skill", "plugin", "adapter", "agent", "gate", "command", "other"]
    subject_name: str
    action: str = ""
    decision: Literal["allow", "agent_decide", "ask_user", "deny"] = "agent_decide"
    risk: Literal["low", "medium", "high"] = "low"
    needs_user: bool = False
    unsafe: bool = False
    policy_id: str = ""
    reason: str
    user_question: str = ""
    agent_action: str = ""


class PermissionPolicyReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    decisions: list[PermissionDecision] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    agent_actions: list[str] = Field(default_factory=list)


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(default_factory=lambda: f"SRC-{uuid4().hex[:8]}")
    title: str
    locator: str = ""
    source_type: Literal[
        "url",
        "file",
        "interview",
        "dataset",
        "document",
        "observation",
        "other",
    ] = "other"
    summary: str = ""
    credibility: Literal["low", "medium", "high"] = "medium"
    added_at: str = Field(default_factory=utc_now)


class SourceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class JudgementRecord(BaseModel):
    """A decision the user (or agent) actually made during the goal.

    This is the durable record of *what was decided* — distinct from a surfaced
    ``Decision`` (which only requests input). The dashboard displays these as a
    read-only judgement log, and they are the substrate for later learning a
    user's judgement style for autonomous execution.
    """

    model_config = ConfigDict(extra="forbid")

    judgement_id: str = Field(default_factory=lambda: f"JDG-{uuid4().hex[:8]}")
    question: str
    choice: str
    rationale: str = ""
    decided_by: Literal["user", "agent"] = "user"
    reversible: bool = True
    phase_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    profile_claim_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    recorded_at: str = Field(default_factory=utc_now)


# Who the building-journey explanation is written for. The agent authors the
# always-visible base `statement` at a high-school reading level; `college` and
# `hobbyist` are optional richer framings layered on top (see `journey.reframe`).
Audience = Literal["high_school", "college", "hobbyist"]


class Assumption(BaseModel):
    """A plain-English assumption the agent is leaning on while building.

    The atom of the building journey: "I'm assuming X (``building``) in order to
    make progress on Y (``toward``)." Recorded so a non-technical reader can trace
    *why* the agent did something. ``depends_on`` marks the load-bearing ones —
    the assumptions whose failure would unravel the work (PACERS: "know which ones
    your solution depends on"). ``status`` lets a later event flip an assumption to
    ``validated`` or ``broken`` without losing the original call.
    """

    model_config = ConfigDict(extra="forbid")

    assumption_id: str = Field(default_factory=lambda: f"A-{uuid4().hex[:8]}")
    statement: str
    building: str = ""
    toward: str = ""
    depends_on: bool = False
    status: Literal["holding", "validated", "broken"] = "holding"
    confidence: float = 0.0
    reversible: bool = True
    phase_id: str | None = None
    audience_notes: dict[str, str] = Field(default_factory=dict)
    recorded_at: str = Field(default_factory=utc_now)


class Subproblem(BaseModel):
    """One branch of a problem breakdown: a sub-problem and how it's tackled."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    solves: str = ""
    tasks: list[str] = Field(default_factory=list)
    assumption_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    audience_notes: dict[str, str] = Field(default_factory=dict)


class ProblemBreakdown(BaseModel):
    """The Assess output: how the agent broke a goal or phase into sub-problems.

    Captures the critical-thinking pass — the rephrased problem, the 5-Whys chain
    to the root, a Pause note (did the agent check it wasn't just satisficing?),
    the sub-problems with their tasks and open questions, and an optional system
    view for recurring problems. Keyed by ``breakdown_id`` so re-running Assess on
    a phase replaces rather than duplicates.
    """

    model_config = ConfigDict(extra="forbid")

    breakdown_id: str = Field(default_factory=lambda: f"BD-{uuid4().hex[:8]}")
    phase_id: str | None = None
    problem: str
    whys: list[str] = Field(default_factory=list)
    pause_note: str = ""
    subproblems: list[Subproblem] = Field(default_factory=list)
    system_view: str = ""
    audience_notes: dict[str, str] = Field(default_factory=dict)
    recorded_at: str = Field(default_factory=utc_now)


UserPreferenceArea = Literal[
    "risk",
    "communication",
    "workflow",
    "technical",
    "decision",
    "other",
]


class UserMemoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"UME-{uuid4().hex[:8]}")
    kind: Literal[
        "manual",
        "interview",
        "insights",
        "judgement",
        "interview_prompted",
        "forget",
    ]
    area: UserPreferenceArea = "other"
    summary: str = ""
    source: Literal[
        "manual",
        "post_goal_interview",
        "claude_insights",
        "judgement",
        "system",
    ] = "manual"
    goal_id: str = ""
    confidence: float = 0.5
    target_claim_id: str = ""
    details: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class UserPreferenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    area: UserPreferenceArea = "other"
    statement: str
    confidence: float = 0.0
    evidence_event_ids: list[str] = Field(default_factory=list)
    status: Literal["candidate", "active", "inactive", "forgotten"] = "candidate"
    updated_at: str = Field(default_factory=utc_now)


class UserMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    claims: list[UserPreferenceClaim] = Field(default_factory=list)
    prompted_goal_ids: list[str] = Field(default_factory=list)
    interviewed_goal_ids: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


class PersonalizationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class SourceFreshnessFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["p0", "p1", "p2"]
    source_id: str
    title: str
    source_type: str = "other"
    summary: str
    detail: str = ""
    age_days: int | None = None
    max_age_days: int | None = None
    claim_refs: list[str] = Field(default_factory=list)
    suggested_action: str = ""
    needs_user: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class SourceFreshnessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    passed: bool
    summary: str
    findings: list[SourceFreshnessFinding] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    agent_actions: list[str] = Field(default_factory=list)


class SelfEvolutionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(default_factory=lambda: f"M-{uuid4().hex[:8]}")
    kind: Literal["friction", "gap", "learning", "success"] = "learning"
    area: Literal[
        "adapter",
        "architecture",
        "dashboard",
        "decision",
        "docs",
        "ecosystem",
        "gate",
        "phase",
        "safety",
        "skill",
        "test",
        "other",
    ] = "other"
    note: str
    severity: Literal["low", "medium", "high"] = "medium"
    goal_id: str = ""
    phase_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class SelfEvolutionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str = Field(default_factory=lambda: f"S-{uuid4().hex[:8]}")
    area: str
    title: str
    plain_summary: str
    recommended_change: str
    occurrences: int
    severity: Literal["low", "medium", "high"] = "medium"
    evidence_refs: list[str] = Field(default_factory=list)
    user_visible: bool = False
    suggested_command: str = ""


class SelfEvolutionMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    entries: list[SelfEvolutionEntry] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


class MemorySyncCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(default_factory=lambda: f"MS-{uuid4().hex[:8]}")
    source_label: str
    area: str
    title: str
    plain_summary: str
    recommended_change: str
    occurrences: int
    severity: Literal["low", "medium", "high"] = "medium"
    suggested_command: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    skip_reason: str = ""


class MemorySyncPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    source_label: str
    target_path: str
    dry_run: bool = True
    include_private: bool = False
    candidates: list[MemorySyncCandidate] = Field(default_factory=list)
    skipped: list[MemorySyncCandidate] = Field(default_factory=list)
    imported_count: int = 0
    summary: str
    agent_actions: list[str] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)


class ArchitectureNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    plain_summary: str
    status: Literal["planned", "in_progress", "built", "blocked", "deferred", "removed"] = "planned"
    owner_phase: str | None = None
    user_value: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    technical_notes: list[str] = Field(default_factory=list)


class ArchitectureEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node: str
    to_node: str
    relation: str = "leads_to"
    plain_summary: str = ""


class GoalArchitectureMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    overview: str
    nodes: list[ArchitectureNode] = Field(default_factory=list)
    edges: list[ArchitectureEdge] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


class ArchitectureBriefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    status: Literal["planned", "in_progress", "built", "blocked", "deferred", "removed"]
    plain_summary: str
    owner_phase: str | None = None
    user_value: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    review_focus: str


class ArchitectureBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    status_counts: dict[str, int] = Field(default_factory=dict)
    review_focus: list[str] = Field(default_factory=list)
    evidence_gaps: list[ArchitectureBriefItem] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ArchitectureCheckFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["p0", "p1", "p2"]
    area: Literal["coverage", "evidence", "map"]
    summary: str
    detail: str = ""
    suggested_action: str = ""
    needs_user: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class ArchitectureCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    passed: bool
    summary: str
    findings: list[ArchitectureCheckFinding] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    agent_actions: list[str] = Field(default_factory=list)


class ParallelWorktreeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    branch: str
    head: str = ""
    dirty: bool = False
    changed_files: list[str] = Field(default_factory=list)
    migration_files: list[str] = Field(default_factory=list)
    ahead_base: int = 0
    behind_base: int = 0


class ParallelMergeScan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_branch: str
    active_branch: str
    active_changed_files: list[str] = Field(default_factory=list)
    active_migration_files: list[str] = Field(default_factory=list)
    sibling_worktrees: list[ParallelWorktreeInfo] = Field(default_factory=list)
    overlapping_files: list[str] = Field(default_factory=list)
    overlapping_migrations: list[str] = Field(default_factory=list)


class MergeReadinessFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["p0", "p1", "p2"]
    area: Literal["migration", "branch", "parallel", "evidence", "decision", "architecture"]
    summary: str
    detail: str = ""
    suggested_action: str = ""
    needs_user: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class MergeReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    passed: bool
    summary: str
    findings: list[MergeReadinessFinding] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    agent_actions: list[str] = Field(default_factory=list)
    parallel_scan: ParallelMergeScan | None = None


class GoalIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["p0", "p1", "p2"]
    area: Literal[
        "architecture",
        "decision",
        "checkpoint",
        "evidence",
        "gate",
        "merge",
        "phase",
        "source",
        "state",
        "risk",
    ]
    summary: str
    detail: str = ""
    suggested_action: str = ""
    needs_user: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class GoalIssueReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    passed: bool
    summary: str
    issues: list[GoalIssue] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    agent_actions: list[str] = Field(default_factory=list)


class ModeAPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: Literal["claude", "codex"]
    adapter_ready: bool = False
    adapter_detail: str = ""
    goal_file: str
    dashboard_file: str
    architecture_file: str
    current_phase: str
    phase_title: str
    phase_goal: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    memory_suggestions: list[SelfEvolutionSuggestion] = Field(default_factory=list)
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
    judgements: list[JudgementRecord] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    breakdowns: list[ProblemBreakdown] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    source_claims: list[SourceClaim] = Field(default_factory=list)
    architecture: GoalArchitectureMap | None = None
    blockers: list[str] = Field(default_factory=list)
    learnings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    last_updated: str = Field(default_factory=utc_now)
    event_count: int = 0


Phase.model_rebuild()
DecisionContext.model_rebuild()


class PortableExport(BaseModel):
    """Result of writing the portable, committable goal spec to `.goals/`."""

    model_config = ConfigDict(extra="forbid")

    spec_version: int
    goal_id: str
    state_path: str
    markdown_path: str
    phase_count: int


class ContextSyncResult(BaseModel):
    """Result of syncing the managed goal block into AGENTS.md / CLAUDE.md."""

    model_config = ConfigDict(extra="forbid")

    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)


class NativeGoalEmission(BaseModel):
    """A native stop-condition derived from the current phase's acceptance."""

    model_config = ConfigDict(extra="forbid")

    adapter: Literal["claude", "codex"]
    condition: str
    command: str
    notes: list[str] = Field(default_factory=list)
