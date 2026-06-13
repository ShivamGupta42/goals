from __future__ import annotations

from pathlib import Path

from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.models import (
    GoalScenario,
    GoalSnapshot,
    GoalUseCase,
    GoalUseCaseCoverage,
    GoalUseCaseCoverageReport,
    ScenarioDecision,
    ScenarioDogfoodCase,
    ScenarioDogfoodReport,
    ScenarioEvaluation,
    WorktreeLease,
)
from goals.runtime import default_phases

CURRENT_CAPABILITIES = {
    "adapter_awareness",
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
    status = "partial" if missing else "covered"
    return GoalUseCaseCoverage(
        use_case_id=use_case.use_case_id,
        category=use_case.category,
        status=status,
        supported_capabilities=supported_required,
        missing_capabilities=missing,
        planned_capabilities=list(use_case.planned_capabilities),
        important_user_decisions=list(use_case.important_user_decisions),
        agent_can_decide=list(use_case.agent_can_decide),
        proof_required=list(use_case.proof_required),
        summary=(
            f"{len(supported_required)}/{len(required)} current "
            f"capabilities covered; {len(use_case.planned_capabilities)} future improvement(s) tracked."
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
    if "goals issues" in prompt:
        supported.add("issue_discovery")
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
