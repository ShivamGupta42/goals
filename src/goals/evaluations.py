from __future__ import annotations

from collections import Counter
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from goals.issues import analyze_goal_issues
from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.models import (
    Decision,
    DecisionOption,
    Event,
    EventType,
    Evidence,
    GateVerdict,
    GateResult,
    GoalArchitectureMap,
    GoalIssueStressCase,
    GoalIssueStressReport,
    GoalStatus,
    GoalRehearsalCase,
    GoalRehearsalReport,
    GoalScenario,
    GoalSnapshot,
    GoalUseCase,
    GoalUseCaseCoverage,
    GoalUseCaseCoverageReport,
    Phase,
    PhaseStatus,
    ScenarioDecision,
    ScenarioDogfoodCase,
    ScenarioDogfoodReport,
    ScenarioEvaluation,
    SelfCheckReport,
    SelfCheckSuiteResult,
    SourceClaim,
    SourceRecord,
    WorktreeLease,
)
from goals.runtime import (
    append_event,
    create_goal,
    default_phases,
    emit_dashboard,
    load_active_snapshot,
    run_gate,
    transition_phase,
)

CURRENT_CAPABILITIES = {
    "adapter_awareness",
    "automatic_gap_to_roadmap_patch",
    "architecture_map",
    "automatic_skill_selection",
    "durable_state",
    "end_user_decision_experience",
    "end_user_visualization",
    "evidence_contract",
    "important_decision_filter",
    "issue_discovery",
    "local_safety_check",
    "local_ecosystem_discovery",
    "mode_a_handoff",
    "merge_readiness_check",
    "non_technical_goal_brief",
    "plugin_capability_discovery",
    "phase_plan",
    "project_history_decision_context",
    "registry_awareness",
    "registry_sync_workflow",
    "review_gate",
    "self_evolution_memory",
    "simple_decision_format",
    "source_registry",
    "worktree_isolation",
}

CORE_GOAL_CAPABILITIES = [
    "durable_state",
    "phase_plan",
    "mode_a_handoff",
    "evidence_contract",
    "review_gate",
    "issue_discovery",
    "important_decision_filter",
    "non_technical_goal_brief",
    "end_user_decision_experience",
    "end_user_visualization",
]

DEFAULT_GOAL_SCENARIOS = [
    GoalScenario(
        scenario_id="personal-fitness-reset",
        category="personal",
        objective="Plan a 12-week fitness reset around travel, family commitments, and existing routines.",
        why="Personal goals need private context, reversible planning, and clear user-only decisions.",
        required_capabilities=[
            "durable_state",
            "phase_plan",
            "mode_a_handoff",
            "evidence_contract",
            "end_user_decision_experience",
            "end_user_visualization",
            "review_gate",
            "issue_discovery",
            "important_decision_filter",
            "simple_decision_format",
            "project_history_decision_context",
        ],
        future_capabilities=[],
        decisions=[
            ScenarioDecision(
                title="Health constraints",
                plain_question="Are there medical or injury constraints the agent must not guess about?",
                options=["No constraints", "Use these constraints", "Pause and ask a professional"],
                why_surface="Health and safety constraints are high-risk and personal.",
            ),
            ScenarioDecision(
                title="Schedule details",
                plain_question="Can the agent infer a weekly schedule from notes, or should it ask first?",
                priority="later",
                options=["Infer and document assumptions", "Ask first"],
                why_surface="This is reversible and can usually be handled by the agent.",
            ),
        ],
        agent_can_decide=[
            "Break the goal into weekly phases.",
            "Record assumptions as evidence.",
            "Recommend reversible routine changes.",
        ],
        success_evidence=["Accepted phases", "Known gaps", "User-facing decision summary"],
    ),
    GoalScenario(
        scenario_id="technical-feature-change",
        category="technical",
        objective="Add tags to tasks, update tests, and explain any migration risk.",
        why="Technical goals need worktree isolation, repo checks, evidence, and escalation only for risky choices.",
        required_capabilities=[
            "durable_state",
            "worktree_isolation",
            "phase_plan",
            "mode_a_handoff",
            "evidence_contract",
            "end_user_decision_experience",
            "end_user_visualization",
            "architecture_map",
            "review_gate",
            "issue_discovery",
            "local_safety_check",
            "merge_readiness_check",
            "important_decision_filter",
        ],
        future_capabilities=[],
        decisions=[
            ScenarioDecision(
                title="Migration risk",
                plain_question="Does the user accept a data migration, or should the agent keep tags in existing storage?",
                options=["Allow migration", "Avoid migration", "Ask for a staged plan"],
                why_surface="Data migrations can be hard to reverse.",
            )
        ],
        agent_can_decide=[
            "Inspect tests and implementation files.",
            "Run repository checks.",
            "Record files changed and proof.",
        ],
        success_evidence=[
            "Passing tests",
            "Accepted review gate",
            "Migration risk decision if needed",
        ],
    ),
    GoalScenario(
        scenario_id="business-research-brief",
        category="business",
        objective="Prepare a customer research brief and follow-up plan for a new product idea.",
        why="Business goals need simple progress reporting, source evidence, and a small number of user decisions.",
        required_capabilities=[
            "durable_state",
            "phase_plan",
            "mode_a_handoff",
            "evidence_contract",
            "end_user_decision_experience",
            "end_user_visualization",
            "review_gate",
            "issue_discovery",
            "important_decision_filter",
            "simple_decision_format",
            "project_history_decision_context",
            "source_registry",
        ],
        future_capabilities=[],
        decisions=[
            ScenarioDecision(
                title="Audience focus",
                plain_question="Which customer segment should the agent optimize the brief for?",
                options=["Founders", "Enterprise buyers", "Consumers"],
                why_surface="Wrong audience changes the entire brief.",
            ),
            ScenarioDecision(
                title="Formatting preference",
                plain_question="Should the brief be a memo or slides?",
                priority="later",
                options=["Memo", "Slides"],
                why_surface="The agent can choose a reversible default and note it.",
            ),
        ],
        agent_can_decide=[
            "Draft the brief structure.",
            "Track sources and gaps.",
            "Create follow-up tasks.",
        ],
        success_evidence=["Research evidence", "Decision summary", "Follow-up plan"],
    ),
    GoalScenario(
        scenario_id="goals-self-evolution",
        category="self_evolution",
        objective="Improve Goals after dogfooding it on real personal, technical, and business goals.",
        why="The repo should learn from its own runs and turn repeated friction into small product improvements.",
        required_capabilities=[
            "durable_state",
            "worktree_isolation",
            "phase_plan",
            "mode_a_handoff",
            "evidence_contract",
            "end_user_decision_experience",
            "end_user_visualization",
            "architecture_map",
            "review_gate",
            "issue_discovery",
            "local_safety_check",
            "important_decision_filter",
            "self_evolution_memory",
        ],
        future_capabilities=[],
        decisions=[
            ScenarioDecision(
                title="Scope expansion",
                plain_question="Should this improvement become product behavior now, or stay in the roadmap?",
                options=["Build now", "Roadmap only", "Run another dogfood cycle"],
                why_surface="This changes what the repository promises to users.",
            )
        ],
        agent_can_decide=[
            "Run checks before and after changes.",
            "Record dogfood findings as evidence.",
            "Add tests for repeated friction.",
        ],
        success_evidence=["Scenario evaluation", "New tests", "Roadmap or implementation commit"],
    ),
    GoalScenario(
        scenario_id="ecosystem-skill-plugin-routing",
        category="ecosystem",
        objective="Use available Claude/Codex skills, plugins, and adapters without making the user choose every tool.",
        why="Goals should offer unique value by routing work through existing agent ecosystems while keeping durable state.",
        required_capabilities=[
            "adapter_awareness",
            "registry_awareness",
            "mode_a_handoff",
            "evidence_contract",
            "end_user_decision_experience",
            "end_user_visualization",
            "review_gate",
            "issue_discovery",
            "important_decision_filter",
            "automatic_skill_selection",
            "local_ecosystem_discovery",
            "plugin_capability_discovery",
            "registry_sync_workflow",
        ],
        future_capabilities=[],
        decisions=[
            ScenarioDecision(
                title="Tool permission",
                plain_question="May the agent use an external plugin or connector that changes data outside the repo?",
                options=["Allow this tool", "Use repo-local work only", "Ask again with details"],
                why_surface="External tools can have privacy, cost, or side-effect risk.",
            )
        ],
        agent_can_decide=[
            "Use registry hints to pick likely skills.",
            "Prefer local/reversible work first.",
            "Record missing capability as a learning.",
        ],
        success_evidence=[
            "Adapter prompt",
            "Registry validation",
            "Escalated only high-risk tool choices",
        ],
    ),
]

DEFAULT_GOAL_USE_CASES = [
    GoalUseCase(
        use_case_id="personal-life-planning",
        category="personal",
        objective="Plan a private life change with preferences, constraints, and reversible weekly steps.",
        why="Personal goals need privacy, gentle progress, and only meaningful preference or safety questions.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "simple_decision_format",
            "project_history_decision_context",
        ],
        planned_capabilities=["optional_calendar_context", "private_memory_boundary"],
        important_user_decisions=["Safety constraints", "Non-negotiable preferences"],
        agent_can_decide=["Phase order", "Reversible defaults", "Progress summary wording"],
        proof_required=["Accepted plan", "Known assumptions", "User-facing decision summary"],
    ),
    GoalUseCase(
        use_case_id="technical-repo-change",
        category="technical",
        objective="Change a repository safely while preserving tests, migrations, and architecture intent.",
        why="Technical goals need isolated work, repo-specific checks, and early detection of merge or migration risk.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "worktree_isolation",
            "architecture_map",
            "local_safety_check",
            "merge_readiness_check",
        ],
        planned_capabilities=["parallel_worktree_merge_gates", "code_derived_architecture_checks"],
        important_user_decisions=["Data migration risk", "Breaking API behavior"],
        agent_can_decide=["Implementation route", "Test commands", "Reversible refactors"],
        proof_required=["Changed files", "Passing checks", "Accepted review gate"],
    ),
    GoalUseCase(
        use_case_id="business-research",
        category="business",
        objective="Create a customer, market, or product brief with sources and follow-up actions.",
        why="Business goals need source-backed claims, clear audience decisions, and simple progress reporting.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "source_registry",
            "simple_decision_format",
            "project_history_decision_context",
        ],
        planned_capabilities=["source_freshness_gate", "citation_quality_review"],
        important_user_decisions=["Audience focus", "External source permission"],
        agent_can_decide=["Brief outline", "Follow-up task list", "Reversible formatting choice"],
        proof_required=["Recorded sources", "Source-backed claims", "Decision summary"],
    ),
    GoalUseCase(
        use_case_id="research-learning",
        category="research",
        objective="Learn or research a topic with questions, sources, uncertainty, and a final synthesis.",
        why="Research and learning goals need provenance, uncertainty, and a clear line between fact and judgment.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "source_registry",
            "simple_decision_format",
        ],
        planned_capabilities=["source_freshness_gate", "spaced_recall_outputs"],
        important_user_decisions=["Research depth", "Trusted source boundaries"],
        agent_can_decide=["Reading order", "Summary structure", "Open question list"],
        proof_required=["Sources", "Uncertainty list", "Synthesis or learning artifact"],
    ),
    GoalUseCase(
        use_case_id="creative-production",
        category="creative",
        objective="Produce creative directions, drafts, or visual concepts while keeping approvals clear.",
        why="Creative goals need room for exploration without making every taste choice a blocker.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "automatic_skill_selection",
            "plugin_capability_discovery",
            "registry_awareness",
        ],
        planned_capabilities=["asset_provenance_checks", "creative_variant_comparison"],
        important_user_decisions=[
            "Brand direction",
            "External generation or publishing permission",
        ],
        agent_can_decide=["Variant exploration", "Draft ordering", "Low-risk copy edits"],
        proof_required=["Selected direction", "Rejected alternatives", "Approval notes"],
    ),
    GoalUseCase(
        use_case_id="operations-process",
        category="operations",
        objective="Improve a recurring workflow, checklist, or operations process.",
        why="Operations goals need durable state, clear handoffs, and proof that the new process can be repeated.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "self_evolution_memory",
            "project_history_decision_context",
        ],
        planned_capabilities=["recurring_goal_templates", "handoff_owner_registry"],
        important_user_decisions=["Owner or accountability change", "Process policy change"],
        agent_can_decide=["Checklist wording", "Documentation placement", "Trial run plan"],
        proof_required=["Updated process", "Trial evidence", "Known gaps"],
    ),
    GoalUseCase(
        use_case_id="high-stakes-boundary",
        category="high_stakes",
        objective="Support medical, legal, financial, or safety-adjacent goals without pretending to be a professional.",
        why="High-stakes goals need conservative escalation, source evidence, uncertainty, and plain limits.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "source_registry",
            "important_decision_filter",
            "simple_decision_format",
        ],
        planned_capabilities=["professional_boundary_templates", "mandatory_external_review_gate"],
        important_user_decisions=["Whether to consult a professional", "Risk tolerance"],
        agent_can_decide=["Question list", "Information organization", "Source summary"],
        proof_required=["Sources", "Uncertainty list", "Boundary statement"],
    ),
    GoalUseCase(
        use_case_id="ecosystem-orchestration",
        category="ecosystem",
        objective="Choose Claude/Codex skills, plugins, and adapters without making the user route every step.",
        why="Goals should add unique value by routing through existing agent ecosystems while keeping durable state.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "automatic_skill_selection",
            "local_ecosystem_discovery",
            "plugin_capability_discovery",
            "registry_sync_workflow",
        ],
        planned_capabilities=["cross_agent_recommendation_merge", "permission_policy_registry"],
        important_user_decisions=[
            "External plugin permission",
            "Cost or remote side-effect approval",
        ],
        agent_can_decide=[
            "Registry hint selection",
            "Repo-local fallback",
            "Missing capability memory",
        ],
        proof_required=["Adapter prompt", "Registry validation", "Escalation record"],
    ),
    GoalUseCase(
        use_case_id="self-evolution",
        category="self_evolution",
        objective="Improve Goals after dogfooding real and synthetic goal runs.",
        why="The product should turn repeated friction into small tested improvements.",
        required_capabilities=[
            *CORE_GOAL_CAPABILITIES,
            "self_evolution_memory",
            "local_safety_check",
            "architecture_map",
        ],
        planned_capabilities=["automatic_gap_to_roadmap_patch", "cross_project_memory_sync"],
        important_user_decisions=["Build now or roadmap", "Public product promise change"],
        agent_can_decide=["Small implementation slice", "Test scope", "Docs update"],
        proof_required=["Scenario eval", "Dogfood eval", "Committed improvement"],
    ),
]


def evaluate_goal_scenarios(
    worktree: Path,
    adapter: ModeAAdapter = "claude",
    scenarios: list[GoalScenario] | None = None,
) -> list[ScenarioEvaluation]:
    selected = scenarios or DEFAULT_GOAL_SCENARIOS
    return [_evaluate_one(worktree.resolve(), adapter, scenario) for scenario in selected]


def evaluate_use_case_coverage(
    worktree: Path,
    adapter: ModeAAdapter = "claude",
    use_cases: list[GoalUseCase] | None = None,
) -> GoalUseCaseCoverageReport:
    selected = use_cases or DEFAULT_GOAL_USE_CASES
    snapshot = _scenario_snapshot(worktree.resolve(), DEFAULT_GOAL_SCENARIOS[0])
    plan = build_mode_a_plan(snapshot, adapter)
    supported = _supported_capabilities(
        worktree.resolve(),
        snapshot,
        plan.prompt,
        plan.recommended_checks,
    )
    cases = [_coverage_case(use_case, supported) for use_case in selected]
    partial = [case for case in cases if case.status == "partial"]
    planned = sorted({capability for case in cases for capability in case.planned_capabilities})
    return GoalUseCaseCoverageReport(
        adapter=adapter,
        passed=not partial,
        summary=(
            f"Checked {len(cases)} representative goal use case(s): "
            f"{len(cases) - len(partial)} covered, {len(partial)} partial, "
            f"{len(planned)} planned future capability area(s)."
        ),
        cases=cases,
        recommendations=_coverage_recommendations(cases),
    )


def run_self_check(
    worktree: Path,
    adapters: list[str] | None = None,
    *,
    max_user_decisions: int = 2,
) -> SelfCheckReport:
    """Run the core self-evolution evaluation matrix and summarize next slices."""

    selected = adapters or ["claude", "codex"]
    results = [
        _self_check_one(worktree.resolve(), adapter, max_user_decisions=max_user_decisions)
        for adapter in selected
    ]
    failed = [result for result in results if not _suite_passed(result)]
    next_slices = _self_check_next_slices(results)
    user_findings = _self_check_user_findings(results)
    ecosystem_findings = _self_check_ecosystem_findings(results)
    summary = (
        f"Ran self-check across {len(results)} adapter shape(s): "
        f"{len(results) - len(failed)} pass, {len(failed)} fail. "
        f"Next suggested slice: {next_slices[0] if next_slices else 'keep dogfooding real goals'}."
    )
    return SelfCheckReport(
        passed=not failed,
        summary=summary,
        adapters=results,
        next_slices=next_slices,
        user_experience_findings=user_findings,
        ecosystem_findings=ecosystem_findings,
    )


def render_self_check_report(report: SelfCheckReport) -> str:
    lines = [
        "# Goals Self-Check Report",
        "",
        f"Overall: {'pass' if report.passed else 'fail'}",
        "",
        report.summary,
    ]
    for result in report.adapters:
        lines.extend(
            [
                "",
                f"## {result.adapter}: {'pass' if _suite_passed(result) else 'fail'}",
                "",
                "### Suite Results",
                _bullets(
                    [
                        f"Scenarios: {'pass' if result.scenarios_passed else 'fail'}",
                        f"Dogfood: {'pass' if result.dogfood_passed else 'fail'}",
                        f"Coverage: {'pass' if result.coverage_passed else 'fail'}",
                        f"Rehearsal: {'pass' if result.rehearsal_passed else 'fail'}",
                        f"Issue stress: {'pass' if result.issue_stress_passed else 'fail'}",
                    ]
                ),
                "",
                "### Experience Signals",
                _bullets(
                    [
                        f"User-facing decisions: {result.user_decision_count}",
                        f"Agent-handled decisions: {result.agent_decision_count}",
                        f"Agent repair actions: {result.agent_repair_action_count}",
                        f"Use cases covered: {result.covered_use_cases}",
                        f"Use cases partial: {result.partial_use_cases}",
                    ]
                ),
                "",
                "### Current Gaps",
                _bullets(result.missing_capabilities or ["No current capability gaps found."]),
                "",
                "### Planned Capability Themes",
                _bullets(result.planned_capabilities or ["No planned future themes found."]),
                "",
                "### Recommendations",
                _bullets(result.recommendations),
            ]
        )
    lines.extend(
        [
            "",
            "## Recommended Next Slices",
            "",
            _bullets(report.next_slices or ["Keep dogfooding real goals and record friction."]),
            "",
            "## User Experience Findings",
            "",
            _bullets(report.user_experience_findings),
            "",
            "## Ecosystem Findings",
            "",
            _bullets(report.ecosystem_findings),
        ]
    )
    return "\n".join(lines) + "\n"


def rehearse_goal_lifecycles(
    adapter: ModeAAdapter = "claude",
    scenarios: list[GoalScenario] | None = None,
) -> GoalRehearsalReport:
    selected = scenarios or DEFAULT_GOAL_SCENARIOS
    cases = [_rehearse_one(scenario) for scenario in selected]
    failed = [case for case in cases if case.status == "fail"]
    total_phases = sum(case.phases_accepted for case in cases)
    total_questions = sum(case.user_question_count for case in cases)
    return GoalRehearsalReport(
        adapter=adapter,
        passed=not failed,
        summary=(
            f"Rehearsed {len(cases)} temporary goal lifecycle(s): "
            f"{len(cases) - len(failed)} pass, {len(failed)} fail, "
            f"{total_phases} accepted phase(s), {total_questions} user question(s) waiting."
        ),
        cases=cases,
        recommendations=_rehearsal_recommendations(cases),
    )


def render_rehearsal_report(report: GoalRehearsalReport) -> str:
    lines = [
        "# Goal Lifecycle Rehearsal Report",
        "",
        f"Adapter shape: {report.adapter}",
        f"Overall: {'pass' if report.passed else 'fail'}",
        "",
        report.summary,
        "",
        "This report creates temporary Git repositories and drives real Goals state through phase evidence, review, acceptance, issue discovery, and dashboard rendering.",
    ]
    for case in report.cases:
        lines.extend(
            [
                "",
                f"## {case.scenario_id}: {case.status}",
                "",
                f"Category: {case.category}",
                f"Goal id: {case.goal_id or 'not created'}",
                case.summary,
                "",
                "### Proof Recorded",
                _bullets(case.proof_recorded or ["No proof recorded."]),
            ]
        )
        if case.error:
            lines.extend(["", f"Error: {case.error}"])
    lines.extend(["", "## Recommendations", "", _bullets(report.recommendations)])
    return "\n".join(lines) + "\n"


def stress_goal_issue_discovery(
    worktree: Path,
    adapter: ModeAAdapter = "claude",
) -> GoalIssueStressReport:
    """Run adversarial issue-discovery fixtures against the Goals issue model."""

    base = worktree.resolve()
    cases = [
        _issue_stress_case(
            stress_id="agent-repair-no-user",
            category="agent_repair",
            snapshot=_agent_repair_snapshot(base),
            expected_issue_areas=["evidence", "gate"],
            expected_user_questions=[],
            minimum_agent_actions=3,
        ),
        _issue_stress_case(
            stress_id="decision-filter",
            category="decision",
            snapshot=_decision_filter_snapshot(base),
            expected_issue_areas=["decision"],
            expected_user_questions=["Choose whether a data migration is allowed."],
            forbidden_user_questions=["Choose label wording for the dashboard."],
        ),
        _issue_stress_case(
            stress_id="source-risk-architecture",
            category="context_integrity",
            snapshot=_source_risk_architecture_snapshot(base),
            expected_issue_areas=["architecture", "risk", "source"],
            expected_user_questions=[],
            minimum_agent_actions=3,
        ),
        _issue_stress_case(
            stress_id="merge-readiness",
            category="merge_coordination",
            snapshot=_merge_readiness_snapshot(base),
            expected_issue_areas=["merge"],
            expected_user_questions=[],
            minimum_agent_actions=1,
        ),
        _issue_stress_case(
            stress_id="unsafe-review-escalation",
            category="safety",
            snapshot=_unsafe_review_snapshot(base),
            expected_issue_areas=["gate"],
            expected_user_questions=["P1 latest review is unsafe."],
            minimum_agent_actions=0,
        ),
    ]
    failed = [case for case in cases if not case.passed]
    total_questions = sum(len(case.user_questions) for case in cases)
    total_actions = sum(case.agent_action_count for case in cases)
    return GoalIssueStressReport(
        adapter=adapter,
        passed=not failed,
        summary=(
            f"Stressed {len(cases)} issue-discovery scenario(s): "
            f"{len(cases) - len(failed)} pass, {len(failed)} fail, "
            f"{total_questions} user-facing question(s), {total_actions} agent repair action(s)."
        ),
        cases=cases,
        recommendations=_issue_stress_recommendations(cases),
    )


def render_issue_stress_report(report: GoalIssueStressReport) -> str:
    lines = [
        "# Goal Issue Stress Report",
        "",
        f"Adapter shape: {report.adapter}",
        f"Overall: {'pass' if report.passed else 'fail'}",
        "",
        report.summary,
        "",
        "This report injects broken goal states and verifies that Goals finds blockers, missing proof, unsafe gates, source gaps, and only user-worthy questions.",
    ]
    for case in report.cases:
        verdict = "pass" if case.passed else "fail"
        lines.extend(
            [
                "",
                f"## {case.stress_id}: {verdict}",
                "",
                f"Category: {case.category}",
                case.summary,
                "",
                "### Issue Areas",
                _bullets(
                    [
                        f"Expected: {', '.join(case.expected_issue_areas) or 'none'}",
                        f"Found: {', '.join(case.found_issue_areas) or 'none'}",
                    ]
                ),
                "",
                "### Needs The User",
                _bullets(case.user_questions or ["No important user question surfaced."]),
                "",
                "### Findings",
                _bullets(case.findings or ["No findings."]),
            ]
        )
    lines.extend(["", "## Recommendations", "", _bullets(report.recommendations)])
    return "\n".join(lines) + "\n"


def render_coverage_report(report: GoalUseCaseCoverageReport) -> str:
    lines = [
        "# Goal Use-Case Coverage Report",
        "",
        f"Adapter shape: {report.adapter}",
        f"Overall: {'pass' if report.passed else 'partial'}",
        "",
        report.summary,
        "",
        "This report checks representative goal families so Goals can evolve beyond a narrow coding workflow.",
    ]
    for case in report.cases:
        lines.extend(
            [
                "",
                f"## {case.use_case_id}: {case.status}",
                "",
                f"Category: {case.category}",
                case.summary,
                "",
                "### Important User Decisions",
                _bullets(case.important_user_decisions),
                "",
                "### Agent Can Decide",
                _bullets(case.agent_can_decide),
                "",
                "### Proof Required",
                _bullets(case.proof_required),
                "",
                "### Capability Coverage",
                _bullets(
                    [
                        f"Supported: {', '.join(case.supported_capabilities) or 'none'}",
                        f"Missing: {', '.join(case.missing_capabilities) or 'none'}",
                        f"Planned: {', '.join(case.planned_capabilities) or 'none'}",
                    ]
                ),
            ]
        )
    lines.extend(["", "## Recommendations", "", _bullets(report.recommendations)])
    return "\n".join(lines) + "\n"


def _self_check_one(
    worktree: Path,
    adapter: str,
    *,
    max_user_decisions: int,
) -> SelfCheckSuiteResult:
    scenarios = evaluate_goal_scenarios(worktree, adapter=adapter)  # type: ignore[arg-type]
    dogfood = dogfood_goal_scenarios(
        worktree,
        adapter=adapter,  # type: ignore[arg-type]
        max_user_decisions=max_user_decisions,
    )
    coverage = evaluate_use_case_coverage(worktree, adapter=adapter)  # type: ignore[arg-type]
    rehearsal = rehearse_goal_lifecycles(adapter=adapter)  # type: ignore[arg-type]
    issue_stress = stress_goal_issue_discovery(worktree, adapter=adapter)  # type: ignore[arg-type]
    missing = sorted(
        {capability for result in scenarios for capability in result.missing_capabilities}
        | {capability for case in coverage.cases for capability in case.missing_capabilities}
    )
    planned = sorted(
        {capability for result in scenarios for capability in result.planned_capabilities}
        | {capability for case in coverage.cases for capability in case.planned_capabilities}
    )
    failed_rehearsals = [case.scenario_id for case in rehearsal.cases if case.status == "fail"]
    failed_issue_stress = [case.stress_id for case in issue_stress.cases if not case.passed]
    recommendations = _dedupe(
        [
            *dogfood.recommendations,
            *coverage.recommendations,
            *rehearsal.recommendations,
            *issue_stress.recommendations,
        ]
    )
    return SelfCheckSuiteResult(
        adapter=adapter,  # type: ignore[arg-type]
        scenarios_passed=all(result.current_supported for result in scenarios),
        dogfood_passed=dogfood.passed,
        coverage_passed=coverage.passed,
        rehearsal_passed=rehearsal.passed,
        issue_stress_passed=issue_stress.passed,
        user_decision_count=sum(case.user_decision_count for case in dogfood.cases),
        agent_decision_count=sum(case.agent_decision_count for case in dogfood.cases),
        agent_repair_action_count=sum(case.agent_action_count for case in issue_stress.cases),
        covered_use_cases=len([case for case in coverage.cases if case.status == "covered"]),
        partial_use_cases=len([case for case in coverage.cases if case.status == "partial"]),
        failed_rehearsals=failed_rehearsals,
        failed_issue_stress_cases=failed_issue_stress,
        missing_capabilities=missing,
        planned_capabilities=planned,
        recommendations=recommendations,
    )


def _suite_passed(result: SelfCheckSuiteResult) -> bool:
    return all(
        [
            result.scenarios_passed,
            result.dogfood_passed,
            result.coverage_passed,
            result.rehearsal_passed,
            result.issue_stress_passed,
        ]
    )


def _self_check_next_slices(results: list[SelfCheckSuiteResult]) -> list[str]:
    missing = Counter(
        capability for result in results for capability in result.missing_capabilities
    )
    if missing:
        return [
            f"Close current capability gap: {_human_capability(capability)}"
            for capability, _ in missing.most_common(5)
        ]
    planned = Counter(
        capability for result in results for capability in result.planned_capabilities
    )
    return [
        f"Explore planned capability: {_human_capability(capability)}"
        for capability, _ in _rank_capabilities(planned)[:5]
    ]


def _self_check_user_findings(results: list[SelfCheckSuiteResult]) -> list[str]:
    findings = []
    for result in results:
        findings.append(
            f"{result.adapter} surfaced {result.user_decision_count} important user decision(s) "
            f"and kept {result.agent_decision_count} routine decision(s) with the agent."
        )
        findings.append(
            f"{result.adapter} issue stress produced {result.agent_repair_action_count} "
            "agent-side repair action(s)."
        )
    return findings


def _self_check_ecosystem_findings(results: list[SelfCheckSuiteResult]) -> list[str]:
    findings = []
    for result in results:
        planned = [
            capability
            for capability in result.planned_capabilities
            if "ecosystem" in capability
            or "plugin" in capability
            or "registry" in capability
            or "permission" in capability
        ]
        if planned:
            findings.append(
                f"{result.adapter} ecosystem future themes: "
                + ", ".join(_human_capability(capability) for capability in planned[:4])
            )
        else:
            findings.append(f"{result.adapter} has no current ecosystem capability gap.")
    return findings


def _human_capability(capability: str) -> str:
    labels = {
        "asset_provenance_checks": "asset provenance checks",
        "automatic_gap_to_roadmap_patch": "automatic gap-to-roadmap patches",
        "citation_quality_review": "citation quality review",
        "code_derived_architecture_checks": "code-derived architecture checks",
        "cross_agent_recommendation_merge": "cross-agent recommendation merge",
        "cross_project_memory_sync": "cross-project memory sync",
        "handoff_owner_registry": "handoff owner registry",
        "mandatory_external_review_gate": "mandatory external review gate",
        "optional_calendar_context": "optional calendar context",
        "parallel_worktree_merge_gates": "parallel worktree merge gates",
        "permission_policy_registry": "permission policy registry",
        "private_memory_boundary": "private memory boundary",
        "professional_boundary_templates": "professional boundary templates",
        "recurring_goal_templates": "recurring goal templates",
        "source_freshness_gate": "source freshness gate",
        "spaced_recall_outputs": "spaced recall outputs",
    }
    return labels.get(capability, capability.replace("_", " "))


def _rank_capabilities(counter: Counter[str]) -> list[tuple[str, int]]:
    priority = {
        "automatic_gap_to_roadmap_patch": 0,
        "parallel_worktree_merge_gates": 1,
        "cross_agent_recommendation_merge": 2,
        "permission_policy_registry": 3,
        "source_freshness_gate": 4,
        "cross_project_memory_sync": 5,
        "professional_boundary_templates": 6,
    }
    return sorted(
        counter.items(),
        key=lambda item: (-item[1], priority.get(item[0], 100), item[0]),
    )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _rehearse_one(scenario: GoalScenario) -> GoalRehearsalCase:
    try:
        with TemporaryDirectory(prefix="goals-rehearsal-") as tmp:
            repo = _init_rehearsal_repo(Path(tmp) / "repo")
            snapshot = create_goal(scenario.objective, repo, why=scenario.why)
            worktree = Path(snapshot.topology.worktree_path)
            if scenario.category == "business":
                _record_rehearsal_source(worktree, snapshot.goal_id)
            proof: list[str] = []
            for phase in snapshot.phases:
                transition_phase(worktree, phase.phase_id, "start")
                evidence = Evidence(
                    changed_files=["README.md"],
                    checks_run=["synthetic rehearsal check"],
                    acceptance_met=phase.acceptance_criteria or ["Phase acceptance satisfied."],
                    source_ids=["SRC-rehearsal"] if scenario.category == "business" else [],
                    confidence=0.9,
                    notes=f"Rehearsal evidence for {phase.phase_id}: {phase.title}.",
                )
                append_event(
                    worktree,
                    Event(
                        goal_id=snapshot.goal_id,
                        event_type=EventType.PHASE_EVIDENCE,
                        payload={
                            "phase_id": phase.phase_id,
                            "evidence": evidence.model_dump(),
                        },
                    ),
                )
                review = run_gate(worktree, phase.phase_id)
                if review.verdict != GateVerdict.PASS:
                    raise RuntimeError(f"{phase.phase_id} review did not pass: {review.summary}")
                transition_phase(worktree, phase.phase_id, "accept")
                proof.append(f"{phase.phase_id}: evidence, passing review, accepted")
            dashboard = emit_dashboard(worktree)
            final_snapshot = load_active_snapshot(worktree)
            issues = analyze_goal_issues(final_snapshot)
            if not issues.passed:
                raise RuntimeError(issues.summary)
            return GoalRehearsalCase(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                status="pass",
                goal_id=final_snapshot.goal_id,
                phases_accepted=len(
                    [
                        phase
                        for phase in final_snapshot.phases
                        if phase.status == PhaseStatus.ACCEPTED
                    ]
                ),
                dashboard_rendered=dashboard.exists(),
                issue_count=len(issues.issues),
                user_question_count=len(issues.user_questions),
                proof_recorded=proof,
                summary=(
                    f"Accepted {len(proof)} phase(s), rendered dashboard, and finished with "
                    f"{len(issues.issues)} issue(s)."
                ),
            )
    except Exception as exc:  # noqa: BLE001
        return GoalRehearsalCase(
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            status="fail",
            summary="Lifecycle rehearsal failed.",
            error=str(exc),
        )


def _init_rehearsal_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _run(["git", "init"], path)
    _run(["git", "config", "user.email", "rehearsal@example.com"], path)
    _run(["git", "config", "user.name", "Goals Rehearsal"], path)
    (path / "README.md").write_text("# Rehearsal\n")
    (path / "LICENSE").write_text("MIT\n")
    _run(["git", "add", "README.md", "LICENSE"], path)
    _run(["git", "commit", "-m", "init rehearsal"], path)
    return path


def _record_rehearsal_source(worktree: Path, goal_id: str) -> None:
    source = SourceRecord(
        source_id="SRC-rehearsal",
        title="Synthetic customer source",
        source_type="interview",
        summary="Synthetic source used to rehearse source-backed business goals.",
        credibility="medium",
    )
    claim = SourceClaim(
        claim="Synthetic customers need simple progress.",
        source_ids=["SRC-rehearsal"],
        confidence=0.8,
    )
    append_event(
        worktree,
        Event(
            goal_id=goal_id,
            event_type=EventType.SOURCE_RECORDED,
            payload={"source": source.model_dump(), "claims": [claim.model_dump()]},
        ),
    )


def _run(args: list[str], cwd: Path) -> None:
    try:
        subprocess.run(
            args,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "no stderr"
        raise RuntimeError(f"{' '.join(args)} failed in {cwd}: {stderr}") from exc


def _rehearsal_recommendations(cases: list[GoalRehearsalCase]) -> list[str]:
    failed = [case for case in cases if case.status == "fail"]
    if failed:
        return [f"Fix rehearsal for {case.scenario_id}: {case.error}" for case in failed]
    return [
        "Keep lifecycle rehearsal in the merge checklist for self-evolution phases.",
        "Add new rehearsal scenarios when a new goal family needs real runtime proof.",
        "Use failures here to improve phases, gates, issue discovery, or public docs.",
    ]


def _issue_stress_case(
    *,
    stress_id: str,
    category: str,
    snapshot: GoalSnapshot,
    expected_issue_areas: list[str],
    expected_user_questions: list[str],
    forbidden_user_questions: list[str] | None = None,
    minimum_agent_actions: int = 0,
) -> GoalIssueStressCase:
    report = analyze_goal_issues(snapshot)
    found_issue_areas = sorted({str(issue.area) for issue in report.issues})
    forbidden = forbidden_user_questions or []
    missing_issue_areas = [area for area in expected_issue_areas if area not in found_issue_areas]
    missing_user_questions = [
        question for question in expected_user_questions if question not in report.user_questions
    ]
    unexpected_user_questions = [
        question
        for question in report.user_questions
        if question not in expected_user_questions or question in forbidden
    ]
    findings: list[str] = []
    if missing_issue_areas:
        findings.append(f"Missing issue areas: {', '.join(missing_issue_areas)}.")
    if missing_user_questions:
        findings.append(f"Missing user questions: {', '.join(missing_user_questions)}.")
    if unexpected_user_questions:
        findings.append(f"Unexpected user questions: {', '.join(unexpected_user_questions)}.")
    if len(report.agent_actions) < minimum_agent_actions:
        findings.append(
            f"Expected at least {minimum_agent_actions} agent repair action(s), "
            f"found {len(report.agent_actions)}."
        )
    passed = not findings
    return GoalIssueStressCase(
        stress_id=stress_id,
        category=category,
        passed=passed,
        issue_report_passed=report.passed,
        expected_issue_areas=expected_issue_areas,
        found_issue_areas=found_issue_areas,
        expected_user_questions=expected_user_questions,
        user_questions=report.user_questions,
        agent_action_count=len(report.agent_actions),
        minimum_agent_actions=minimum_agent_actions,
        missing_issue_areas=missing_issue_areas,
        missing_user_questions=missing_user_questions,
        unexpected_user_questions=unexpected_user_questions,
        findings=findings,
        summary=(
            f"Found {len(report.issues)} issue(s), "
            f"{len(report.user_questions)} user question(s), "
            f"and {len(report.agent_actions)} agent action(s)."
        ),
    )


def _agent_repair_snapshot(base: Path) -> GoalSnapshot:
    return _stress_snapshot(
        base,
        "agent-repair-no-user",
        "Recover a technical goal with incomplete proof without bothering the user.",
        phases=[
            Phase(
                phase_id="P1",
                title="Implementation proof",
                goal="Prove the work is ready for review.",
                status=PhaseStatus.NEEDS_REVIEW,
                evidence=Evidence(
                    changed_files=["src/app.py"],
                    acceptance_not_met=["Tests have not run."],
                    ambiguous=["Migration numbering has not been checked."],
                    confidence=0.4,
                    notes="Partial evidence deliberately missing checks.",
                ),
            )
        ],
        current_phase="P1",
    )


def _decision_filter_snapshot(base: Path) -> GoalSnapshot:
    return _stress_snapshot(
        base,
        "decision-filter",
        "Verify only consequential decisions are surfaced to the user.",
        phases=[
            Phase(
                phase_id="P1",
                title="Decision triage",
                goal="Separate user decisions from reversible agent choices.",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    changed_files=["dashboard.html"],
                    checks_run=["pytest tests/test_decisions.py"],
                    acceptance_met=["Decision rules exercised."],
                    confidence=0.9,
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.PASS,
                        summary="Decision filtering proof is complete.",
                    )
                ],
            )
        ],
        current_phase="P1",
        decisions=[
            Decision(
                title="Migration approval",
                plain_summary="Choose whether a data migration is allowed.",
                why_it_matters="A migration can change production data and may be hard to undo.",
                recommendation="Avoid migration until the user approves it.",
                options=[
                    DecisionOption(
                        label="Add migration",
                        explanation="Change stored data shape.",
                        risk="high",
                        reversible=False,
                    ),
                    DecisionOption(
                        label="Avoid migration",
                        explanation="Use an existing compatible storage shape.",
                        risk="low",
                        reversible=True,
                    ),
                ],
                priority="blocking",
                suggested_reply="Avoid migration for now.",
            ),
            Decision(
                title="Dashboard label wording",
                plain_summary="Choose label wording for the dashboard.",
                why_it_matters="This affects wording, not the goal outcome.",
                recommendation="Use the shorter label.",
                options=[
                    DecisionOption(
                        label="Use shorter label",
                        explanation="Keep the dashboard easier to scan.",
                        risk="low",
                        reversible=True,
                    )
                ],
                priority="later",
                suggested_reply="Use the shorter label.",
            ),
        ],
    )


def _source_risk_architecture_snapshot(base: Path) -> GoalSnapshot:
    return _stress_snapshot(
        base,
        "source-risk-architecture",
        "Find context integrity issues without escalating routine repairs.",
        phases=[
            Phase(
                phase_id="P1",
                title="Research synthesis",
                goal="Connect claims, risks, and architecture questions.",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    changed_files=["docs/research.md"],
                    checks_run=["manual source review"],
                    acceptance_met=["Synthesis drafted."],
                    confidence=0.8,
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.PASS,
                        summary="Research synthesis has enough local proof.",
                    )
                ],
            )
        ],
        current_phase="P1",
        source_claims=[
            SourceClaim(
                claim="Customers need progress that non-technical users can understand.",
                source_ids=["SRC-missing"],
                confidence=0.8,
            ),
            SourceClaim(
                claim="Architecture diagrams reduce review friction.",
                source_ids=[],
                confidence=0.3,
            ),
        ],
        risks=["Source freshness has not been checked."],
        architecture=GoalArchitectureMap(
            title="Issue stress architecture",
            overview="Synthetic architecture map with an unresolved ownership question.",
            questions=["Which component owns source freshness review?"],
        ),
    )


def _unsafe_review_snapshot(base: Path) -> GoalSnapshot:
    return _stress_snapshot(
        base,
        "unsafe-review-escalation",
        "Escalate unsafe review results instead of letting the agent continue alone.",
        phases=[
            Phase(
                phase_id="P1",
                title="Destructive operation",
                goal="Avoid irreversible actions unless clearly approved.",
                status=PhaseStatus.NEEDS_REVIEW,
                evidence=Evidence(
                    changed_files=["scripts/cleanup.sh"],
                    checks_run=["shellcheck scripts/cleanup.sh"],
                    acceptance_met=["Cleanup script drafted."],
                    confidence=0.9,
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.UNSAFE,
                        summary="Proposed cleanup can delete user data.",
                    )
                ],
            )
        ],
        current_phase="P1",
    )


def _merge_readiness_snapshot(base: Path) -> GoalSnapshot:
    return _stress_snapshot(
        base,
        "merge-readiness",
        "Catch migration ordering risk before a coordinator merges parallel technical work.",
        phases=[
            Phase(
                phase_id="P1",
                title="Migration change",
                goal="Record merge-sensitive proof for a migration change.",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    changed_files=["db/migrations/0108_add_tags.py"],
                    checks_run=["pytest tests/test_tasks.py"],
                    acceptance_met=["Tags work in tests."],
                    confidence=0.9,
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.PASS,
                        summary="Feature proof exists, but merge-readiness is intentionally incomplete.",
                    )
                ],
            )
        ],
        current_phase="P1",
    )


def _stress_snapshot(
    base: Path,
    stress_id: str,
    objective: str,
    *,
    phases: list[Phase],
    current_phase: str | None,
    decisions: list[Decision] | None = None,
    source_claims: list[SourceClaim] | None = None,
    risks: list[str] | None = None,
    architecture: GoalArchitectureMap | None = None,
) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id=f"stress-{stress_id}",
        objective=objective,
        why="Synthetic issue-discovery stress case.",
        definition_of_done=["Expected issues are classified correctly."],
        status=GoalStatus.ACTIVE,
        topology=WorktreeLease(
            base_repo=str(base),
            base_branch="main",
            worktree_path=str(base),
            branch=f"stress/{stress_id}",
        ),
        phases=phases,
        current_phase=current_phase,
        decisions=decisions or [],
        source_claims=source_claims or [],
        risks=risks or [],
        architecture=architecture,
    )


def _issue_stress_recommendations(cases: list[GoalIssueStressCase]) -> list[str]:
    failed = [case for case in cases if not case.passed]
    if failed:
        return [
            f"Fix issue stress case {case.stress_id}: {', '.join(case.findings)}" for case in failed
        ]
    return [
        "Keep issue stress evaluation in the merge checklist with lifecycle rehearsal.",
        "Add a stress case whenever a new issue area or decision rule is added.",
        "Treat unexpected user questions as product friction, not just test failures.",
    ]


def dogfood_goal_scenarios(
    worktree: Path,
    adapter: ModeAAdapter = "claude",
    scenarios: list[GoalScenario] | None = None,
    *,
    max_user_decisions: int = 2,
) -> ScenarioDogfoodReport:
    selected = scenarios or DEFAULT_GOAL_SCENARIOS
    evaluations = evaluate_goal_scenarios(worktree, adapter=adapter, scenarios=selected)
    cases = [
        _dogfood_case(scenario, evaluation, max_user_decisions=max_user_decisions)
        for scenario, evaluation in zip(selected, evaluations, strict=True)
    ]
    passed = all(case.status == "pass" for case in cases)
    total_user_decisions = sum(case.user_decision_count for case in cases)
    total_agent_decisions = sum(case.agent_decision_count for case in cases)
    failing = [case.scenario_id for case in cases if case.status == "fail"]
    return ScenarioDogfoodReport(
        adapter=adapter,
        passed=passed,
        summary=(
            f"Dogfooded {len(cases)} synthetic goal type(s): "
            f"{len(cases) - len(failing)} pass, {len(failing)} fail, "
            f"{total_user_decisions} user-facing decision(s), "
            f"{total_agent_decisions} agent-handled decision(s)."
        ),
        cases=cases,
        recommendations=_dogfood_recommendations(cases),
    )


def _coverage_case(use_case: GoalUseCase, supported: set[str]) -> GoalUseCaseCoverage:
    required = set(use_case.required_capabilities)
    supported_required = sorted(required & supported)
    missing = sorted(required - supported)
    planned = [
        capability for capability in use_case.planned_capabilities if capability not in supported
    ]
    status = "partial" if missing else "covered"
    return GoalUseCaseCoverage(
        use_case_id=use_case.use_case_id,
        category=use_case.category,
        status=status,
        supported_capabilities=supported_required,
        missing_capabilities=missing,
        planned_capabilities=planned,
        important_user_decisions=list(use_case.important_user_decisions),
        agent_can_decide=list(use_case.agent_can_decide),
        proof_required=list(use_case.proof_required),
        summary=(
            f"{len(supported_required)}/{len(required)} current "
            f"capabilities covered; {len(planned)} future improvement(s) tracked."
        ),
    )


def _coverage_recommendations(cases: list[GoalUseCaseCoverage]) -> list[str]:
    partial = [case for case in cases if case.status == "partial"]
    if partial:
        return [
            f"Close current capability gaps for {case.use_case_id}: {', '.join(case.missing_capabilities)}."
            for case in partial
        ]
    return [
        "Keep adding a coverage row when a new user goal family appears.",
        "Turn repeated planned capability mentions into roadmap entries or small implementation slices.",
        "Pair `goals eval coverage` with `goals eval dogfood` before merging self-evolution phases.",
    ]


def render_dogfood_report(report: ScenarioDogfoodReport) -> str:
    lines = [
        "# Goals Dogfood Report",
        "",
        f"Adapter shape: {report.adapter}",
        f"Overall: {'pass' if report.passed else 'fail'}",
        "",
        report.summary,
        "",
        "This report uses synthetic scenarios to check whether Goals keeps the agent moving, "
        "surfaces only important user decisions, and records the proof needed for review.",
    ]
    for case in report.cases:
        lines.extend(
            [
                "",
                f"## {case.scenario_id}: {case.status}",
                "",
                f"Category: {case.category}",
                f"Objective: {case.objective}",
                "",
                case.plain_summary,
                "",
                "### What the user sees",
                _bullets(case.surfaced_questions or ["No user decision is required."]),
                "",
                "### What the agent can decide",
                _bullets(case.agent_handled_decisions or ["No agent-handled choices recorded."]),
                "",
                "### Proof required",
                _bullets(case.required_evidence or ["No proof items recorded."]),
                "",
                "### Findings",
                _bullets(case.findings or ["No findings."]),
            ]
        )
    lines.extend(["", "## Recommendations", "", _bullets(report.recommendations)])
    return "\n".join(lines) + "\n"


def _evaluate_one(
    worktree: Path, adapter: ModeAAdapter, scenario: GoalScenario
) -> ScenarioEvaluation:
    snapshot = _scenario_snapshot(worktree, scenario)
    plan = build_mode_a_plan(snapshot, adapter)
    supported = _supported_capabilities(worktree, snapshot, plan.prompt, plan.recommended_checks)
    missing = sorted(set(scenario.required_capabilities) - supported)
    surfaced = [decision for decision in scenario.decisions if decision.priority == "blocking"]
    agent_decisions = list(scenario.agent_can_decide)
    agent_decisions.extend(
        decision.title for decision in scenario.decisions if decision.priority != "blocking"
    )
    return ScenarioEvaluation(
        scenario_id=scenario.scenario_id,
        category=scenario.category,
        current_supported=not missing,
        supported_capabilities=sorted(set(scenario.required_capabilities) & supported),
        missing_capabilities=missing,
        planned_capabilities=scenario.future_capabilities,
        surfaced_decisions=surfaced,
        agent_decisions=agent_decisions,
        summary=(
            f"{scenario.category} scenario supports "
            f"{len(set(scenario.required_capabilities) & supported)}/{len(scenario.required_capabilities)} "
            f"current capabilities and surfaces {len(surfaced)} blocking decision(s)."
        ),
    )


def _dogfood_case(
    scenario: GoalScenario,
    evaluation: ScenarioEvaluation,
    *,
    max_user_decisions: int,
) -> ScenarioDogfoodCase:
    surfaced_questions = [decision.plain_question for decision in evaluation.surfaced_decisions]
    agent_handled = list(evaluation.agent_decisions)
    findings: list[str] = []
    blocking_expected = [
        decision for decision in scenario.decisions if decision.priority == "blocking"
    ]
    later_or_reversible = [
        decision for decision in scenario.decisions if decision.priority != "blocking"
    ]

    if evaluation.missing_capabilities:
        findings.append(f"Missing capabilities: {', '.join(evaluation.missing_capabilities)}.")
    if len(surfaced_questions) > max_user_decisions:
        findings.append(
            f"Surfaces {len(surfaced_questions)} user decisions; target is {max_user_decisions} or fewer."
        )
    if blocking_expected and len(surfaced_questions) != len(blocking_expected):
        findings.append(
            "Blocking decision coverage is incomplete; every blocking decision should be visible."
        )
    leaked_later = [
        decision.plain_question
        for decision in later_or_reversible
        if decision.plain_question in surfaced_questions
    ]
    if leaked_later:
        findings.append(
            "Reversible or later decisions leaked to the user: " + ", ".join(leaked_later) + "."
        )
    if not agent_handled:
        findings.append("No agent-handled decisions are documented.")
    if not scenario.success_evidence:
        findings.append("No success evidence is defined.")

    status = "fail" if findings else "pass"
    return ScenarioDogfoodCase(
        scenario_id=scenario.scenario_id,
        category=scenario.category,
        objective=scenario.objective,
        status=status,
        plain_summary=(
            f"This {scenario.category} goal surfaces {len(surfaced_questions)} important "
            f"user decision(s), leaves {len(agent_handled)} reversible or execution "
            f"choice(s) to the agent, and requires {len(scenario.success_evidence)} proof item(s)."
        ),
        user_decision_count=len(surfaced_questions),
        agent_decision_count=len(agent_handled),
        surfaced_questions=surfaced_questions,
        agent_handled_decisions=agent_handled,
        required_evidence=list(scenario.success_evidence),
        missing_capabilities=list(evaluation.missing_capabilities),
        findings=findings,
    )


def _dogfood_recommendations(cases: list[ScenarioDogfoodCase]) -> list[str]:
    failing = [case for case in cases if case.status == "fail"]
    if not failing:
        return [
            "Continue running real personal, technical, and business goals through Mode A.",
            "Record repeated friction with `goals memory record` so self-evolution suggestions become evidence-backed.",
            "Add a scenario when a new user type or agent ecosystem behavior appears.",
        ]
    recommendations = []
    for case in failing:
        recommendations.append(f"Fix {case.scenario_id}: " + " ".join(case.findings[:2]))
    return recommendations


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _scenario_snapshot(worktree: Path, scenario: GoalScenario) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id=scenario.scenario_id,
        objective=scenario.objective,
        why=scenario.why,
        topology=WorktreeLease(
            base_repo=str(worktree),
            base_branch="main",
            worktree_path=str(worktree),
            branch=f"goal/{scenario.scenario_id}",
        ),
        phases=default_phases(scenario.objective),
        current_phase="P1",
    )


def _supported_capabilities(
    worktree: Path,
    snapshot: GoalSnapshot,
    prompt: str,
    recommended_checks: list[str],
) -> set[str]:
    supported = set()
    if ".agent-workflow/goals" in prompt and "goal.json" in prompt:
        supported.add("durable_state")
    if "Dashboard:" in prompt and "dashboard.html" in prompt:
        supported.add("end_user_visualization")
    if "Architecture map:" in prompt and "architecture.md" in prompt:
        supported.add("architecture_map")
    if "Recommended skills/plugins for this phase:" in prompt:
        supported.add("automatic_skill_selection")
    if "goals ecosystem discover" in prompt:
        supported.add("local_ecosystem_discovery")
    if "skills/plugins/adapters" in prompt and "goals ecosystem discover" in prompt:
        supported.add("plugin_capability_discovery")
    if "goals ecosystem sync" in prompt:
        supported.add("registry_sync_workflow")
    if "goals roadmap suggest" in prompt:
        supported.add("automatic_gap_to_roadmap_patch")
    if "goals issues" in prompt:
        supported.add("issue_discovery")
    if "goals merge-check" in prompt or any(
        "goals merge-check" in check for check in recommended_checks
    ):
        supported.add("merge_readiness_check")
    if "goals brief" in prompt or any("goals brief" in check for check in recommended_checks):
        supported.add("non_technical_goal_brief")
    if "Self-evolution memory:" in prompt and "goals memory record" in prompt:
        supported.add("self_evolution_memory")
    if "Source evidence:" in prompt and "goals source add" in prompt:
        supported.add("source_registry")
    if snapshot.topology.branch.startswith("goal/") and snapshot.topology.worktree_path:
        supported.add("worktree_isolation")
    if snapshot.current_phase and snapshot.phases and "Acceptance criteria:" in prompt:
        supported.add("phase_plan")
    if prompt.startswith("/goal") and "Required loop:" in prompt:
        supported.add("mode_a_handoff")
    if "Evidence JSON shape:" in prompt and "goals phase evidence" in prompt:
        supported.add("evidence_contract")
    if "goals phase review" in prompt and "goals phase accept" in prompt:
        supported.add("review_gate")
    if any("safety-check --mode local" in check for check in recommended_checks):
        supported.add("local_safety_check")
    if "Mode A adapter:" in prompt and (
        "Claude Mode A notes:" in prompt or "Codex Mode A notes:" in prompt
    ):
        supported.add("adapter_awareness")
    if _has_registries(worktree):
        supported.add("registry_awareness")
    supported.add("important_decision_filter")
    supported.add("simple_decision_format")
    supported.add("end_user_decision_experience")
    supported.add("project_history_decision_context")
    return supported


def _has_registries(worktree: Path) -> bool:
    registry_root = worktree / "registries"
    required = {
        "adapters.yml",
        "agents.yml",
        "gates.yml",
        "plugins.yml",
        "profiles.yml",
        "skills.yml",
    }
    return registry_root.exists() and required.issubset(
        {path.name for path in registry_root.glob("*.yml")}
    )
