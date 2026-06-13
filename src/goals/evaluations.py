from __future__ import annotations

from pathlib import Path

from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.models import (
    GoalScenario,
    GoalSnapshot,
    ScenarioDecision,
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
    "local_safety_check",
    "local_ecosystem_discovery",
    "mode_a_handoff",
    "phase_plan",
    "project_history_decision_context",
    "registry_awareness",
    "registry_sync_workflow",
    "review_gate",
    "self_evolution_memory",
    "simple_decision_format",
    "worktree_isolation",
}

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
            "important_decision_filter",
            "simple_decision_format",
            "project_history_decision_context",
        ],
        future_capabilities=["source_registry"],
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
            "important_decision_filter",
            "automatic_skill_selection",
            "local_ecosystem_discovery",
            "registry_sync_workflow",
        ],
        future_capabilities=["plugin_capability_discovery"],
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


def evaluate_goal_scenarios(
    worktree: Path,
    adapter: ModeAAdapter = "claude",
    scenarios: list[GoalScenario] | None = None,
) -> list[ScenarioEvaluation]:
    selected = scenarios or DEFAULT_GOAL_SCENARIOS
    return [_evaluate_one(worktree.resolve(), adapter, scenario) for scenario in selected]


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
    if "goals ecosystem sync" in prompt:
        supported.add("registry_sync_workflow")
    if "Self-evolution memory:" in prompt and "goals memory record" in prompt:
        supported.add("self_evolution_memory")
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
