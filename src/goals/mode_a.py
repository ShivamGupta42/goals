from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from goals.adapters import adapter_check
from goals.ecosystem import recommend_ecosystem_tools, render_recommendations
from goals.memory import derive_memory_suggestions, load_memory, render_memory_suggestions
from goals.models import Evidence, GoalSnapshot, ModeAPlan, Phase
from goals.storage import GoalsError

ModeAAdapter = Literal["auto", "claude", "codex"]


def build_mode_a_plan(snapshot: GoalSnapshot, adapter: ModeAAdapter = "auto") -> ModeAPlan:
    selected, ready, detail = resolve_mode_a_adapter(adapter)
    phase = _current_phase(snapshot)
    worktree = Path(snapshot.topology.worktree_path)
    goal_dir = worktree / ".agent-workflow" / "goals" / snapshot.goal_id
    checks = recommended_checks(worktree)
    recommended_tools = recommend_ecosystem_tools(worktree, snapshot)
    memory_suggestions = derive_memory_suggestions(load_memory(worktree, snapshot))[:5]
    evidence_file = goal_dir / f"evidence-{phase.phase_id.lower()}.json"
    evidence = Evidence(
        changed_files=[],
        checks_run=checks,
        acceptance_met=[],
        known_gaps=[],
        confidence=0.0,
        notes=f"Evidence for {phase.phase_id}: {phase.title}",
    )
    plan = ModeAPlan(
        adapter=selected,
        adapter_ready=ready,
        adapter_detail=detail,
        goal_file=str(goal_dir / "goal.json"),
        dashboard_file=str(goal_dir / "dashboard.html"),
        architecture_file=str(goal_dir / "architecture.md"),
        current_phase=phase.phase_id,
        phase_title=phase.title,
        phase_goal=phase.goal,
        acceptance_criteria=phase.acceptance_criteria,
        recommended_checks=checks,
        recommended_tools=recommended_tools,
        memory_suggestions=memory_suggestions,
        evidence_file=str(evidence_file),
        evidence_template=evidence,
        prompt="",
    )
    return plan.model_copy(update={"prompt": render_mode_a_prompt(snapshot, plan)})


def resolve_mode_a_adapter(adapter: ModeAAdapter) -> tuple[Literal["claude", "codex"], bool, str]:
    if adapter != "auto":
        ready, detail = adapter_check(adapter)
        return adapter, ready, detail
    for candidate in ("claude", "codex"):
        ready, detail = adapter_check(candidate)
        if ready:
            return candidate, ready, detail
    return "claude", False, "No native adapter detected; generated Claude-style instructions."


def recommended_checks(worktree: Path) -> list[str]:
    checks = ["git status --short"]
    pyproject = worktree / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="ignore")
        if "pytest" in text or (worktree / "tests").exists():
            checks.append("uv run pytest -q")
        if "ruff" in text:
            checks.append("uv run ruff check .")
    checks.extend(["uv run goals validate", "uv run goals safety-check --mode local ."])
    return checks


def render_mode_a_prompt(snapshot: GoalSnapshot, plan: ModeAPlan) -> str:
    adapter_notes = _adapter_notes(plan.adapter, plan.adapter_ready, plan.adapter_detail)
    criteria = _bullets(plan.acceptance_criteria)
    checks = _bullets(plan.recommended_checks)
    tools = render_recommendations(plan.recommended_tools)
    memory = render_memory_suggestions(plan.memory_suggestions)
    evidence_json = json.dumps(plan.evidence_template.model_dump(mode="json"), indent=2)
    return f"""/goal Finish this Goals-managed task: {snapshot.objective}

Mode A adapter: {plan.adapter}
Adapter status: {"ready" if plan.adapter_ready else "not confirmed"} - {plan.adapter_detail}

State files:
- Goal snapshot: `{plan.goal_file}`
- Dashboard: `{plan.dashboard_file}`
- Architecture map: `{plan.architecture_file}`
- Evidence draft: `{plan.evidence_file}`

Current phase: {plan.current_phase} - {plan.phase_title}
Phase goal: {plan.phase_goal}

Acceptance criteria:
{criteria}

Required loop:
1. Read `goal.json` before each turn and work only on the current phase.
2. Make reversible progress without changing unrelated files.
3. Keep `architecture.md` current when the phase changes what is built, planned, blocked, or deferred.
4. Put phase evidence in `{plan.evidence_file}` using the JSON shape below.
5. Run `goals phase evidence {plan.current_phase} --file {plan.evidence_file}`.
6. Run `goals phase review {plan.current_phase}`.
7. Only after the review passes, run `goals phase accept {plan.current_phase}`.
8. Run `goals run --adapter {plan.adapter}` before moving to the next phase.

Recommended checks for this repo:
{checks}

Recommended skills/plugins for this phase:
{tools}

Self-evolution memory:
{memory}

Evidence JSON shape:
```json
{evidence_json}
```

{adapter_notes}

If you hit repeated friction, record it with `goals memory record "what happened" --area phase --kind friction` so future runs can improve phases, skills, gates, or docs.

Goals is the durable state and review layer. The native agent goal loop owns persistence of attention; Goals owns phases, evidence, gates, decisions, learnings, memory, and the dashboard.
"""


def _current_phase(snapshot: GoalSnapshot) -> Phase:
    if snapshot.current_phase is None:
        raise GoalsError("Goal has no current phase.")
    for phase in snapshot.phases:
        if phase.phase_id == snapshot.current_phase:
            return phase
    raise GoalsError(f"Current phase not found: {snapshot.current_phase}")


def _adapter_notes(adapter: Literal["claude", "codex"], ready: bool, detail: str) -> str:
    if adapter == "claude":
        return (
            "Claude Mode A notes:\n"
            "- Prefer a narrow context request before broad repository reads.\n"
            "- For non-interactive dry runs, use `claude -p --safe-mode` with an explicit tool list and a realistic budget.\n"
            "- If permissions block progress, choose a reversible local action first and record the blocker as evidence.\n"
            f"- Adapter check detail: {detail if detail else ('ready' if ready else 'not confirmed')}"
        )
    return (
        "Codex Mode A notes:\n"
        "- Use the native `/goal` loop when the local Codex goals feature is enabled.\n"
        "- Keep the plan updated during substantial work and summarize checks after each phase.\n"
        "- If the Codex goals feature is unavailable, paste this prompt into the current Codex session and keep Goals as the state layer.\n"
        f"- Adapter check detail: {detail if detail else ('ready' if ready else 'not confirmed')}"
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None recorded."
