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
    ARCHITECTURE_UPDATED = "architecture_updated"
    SOURCE_RECORDED = "source_recorded"
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


class DecisionExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["basic", "detailed", "technical"]
    surfaced_to_user: bool
    reason_for_surface: str
    markdown: str
    decision: Decision
    context: DecisionContext


class EcosystemRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["skill", "plugin", "adapter", "agent", "gate"]
    name: str
    label: str
    reason: str
    confidence: float = 0.0
    command_hint: str = ""
    source_registry: str
    user_approval_required: bool = False


class DiscoveredTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["skill", "plugin", "adapter"]
    name: str
    label: str
    description: str = ""
    source: str = ""
    registered: bool = False
    available: bool = True
    registry: str = ""
    suggested_registry_entry: dict[str, Any] = Field(default_factory=dict)


class EcosystemDiscoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tools: list[DiscoveredTool] = Field(default_factory=list)
    missing_from_registry: list[DiscoveredTool] = Field(default_factory=list)
    summary: str


class RegistrySyncChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry: str
    kind: Literal["skill", "plugin", "adapter"]
    name: str
    action: Literal["add"] = "add"
    entry: dict[str, Any] = Field(default_factory=dict)


class RegistrySyncPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[RegistrySyncChange] = Field(default_factory=list)
    dry_run: bool = True
    summary: str


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


class ScenarioDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    plain_question: str
    priority: Literal["blocking", "important", "later"] = "blocking"
    options: list[str] = Field(default_factory=list)
    why_surface: str = ""


class GoalScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    category: Literal["personal", "technical", "business", "self_evolution", "ecosystem"]
    objective: str
    why: str
    required_capabilities: list[str] = Field(default_factory=list)
    future_capabilities: list[str] = Field(default_factory=list)
    decisions: list[ScenarioDecision] = Field(default_factory=list)
    agent_can_decide: list[str] = Field(default_factory=list)
    success_evidence: list[str] = Field(default_factory=list)


class ScenarioEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    category: str
    current_supported: bool
    supported_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    planned_capabilities: list[str] = Field(default_factory=list)
    surfaced_decisions: list[ScenarioDecision] = Field(default_factory=list)
    agent_decisions: list[str] = Field(default_factory=list)
    summary: str


class ScenarioDogfoodCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    category: str
    objective: str
    status: Literal["pass", "fail"]
    plain_summary: str
    user_decision_count: int = 0
    agent_decision_count: int = 0
    surfaced_questions: list[str] = Field(default_factory=list)
    agent_handled_decisions: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class ScenarioDogfoodReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: Literal["claude", "codex"]
    passed: bool
    summary: str
    cases: list[ScenarioDogfoodCase] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class GoalUseCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    category: str
    objective: str
    why: str
    required_capabilities: list[str] = Field(default_factory=list)
    planned_capabilities: list[str] = Field(default_factory=list)
    important_user_decisions: list[str] = Field(default_factory=list)
    agent_can_decide: list[str] = Field(default_factory=list)
    proof_required: list[str] = Field(default_factory=list)


class GoalUseCaseCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    category: str
    status: Literal["covered", "partial"]
    supported_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    planned_capabilities: list[str] = Field(default_factory=list)
    important_user_decisions: list[str] = Field(default_factory=list)
    agent_can_decide: list[str] = Field(default_factory=list)
    proof_required: list[str] = Field(default_factory=list)
    summary: str


class GoalUseCaseCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: Literal["claude", "codex"]
    passed: bool
    summary: str
    cases: list[GoalUseCaseCoverage] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class GoalRehearsalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    category: str
    status: Literal["pass", "fail"]
    goal_id: str = ""
    phases_accepted: int = 0
    dashboard_rendered: bool = False
    issue_count: int = 0
    user_question_count: int = 0
    proof_recorded: list[str] = Field(default_factory=list)
    summary: str
    error: str = ""


class GoalRehearsalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter: Literal["claude", "codex"]
    passed: bool
    summary: str
    cases: list[GoalRehearsalCase] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class GoalIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["p0", "p1", "p2"]
    area: Literal[
        "architecture",
        "decision",
        "evidence",
        "gate",
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
    architecture_file: str
    current_phase: str
    phase_title: str
    phase_goal: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    recommended_tools: list[EcosystemRecommendation] = Field(default_factory=list)
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
    sources: list[SourceRecord] = Field(default_factory=list)
    source_claims: list[SourceClaim] = Field(default_factory=list)
    architecture: GoalArchitectureMap | None = None
    blockers: list[str] = Field(default_factory=list)
    learnings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    last_updated: str = Field(default_factory=utc_now)
    event_count: int = 0


Phase.model_rebuild()
