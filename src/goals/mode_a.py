from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from goals.adapters import adapter_check
from goals.memory import derive_memory_suggestions, load_memory, render_memory_suggestions
from goals.models import Evidence, GoalSnapshot, ModeAPlan, Phase, Verification
from goals.sources import render_claim_summary, render_source_summary
from goals.storage import GoalsError
from goals.user_memory import (
    build_personalization_context,
    render_personalization_context,
)

ModeAAdapter = Literal["auto", "claude", "codex"]


def build_mode_a_plan(
    snapshot: GoalSnapshot, adapter: ModeAAdapter = "auto", *, full: bool = True
) -> ModeAPlan:
    selected, ready, detail = resolve_mode_a_adapter(adapter)
    phase = _current_phase(snapshot)
    worktree = Path(snapshot.topology.worktree_path)
    goal_dir = worktree / ".agent-workflow" / "goals" / snapshot.goal_id
    checks = recommended_checks(worktree)
    memory_suggestions = derive_memory_suggestions(load_memory(worktree, snapshot))[:5]
    evidence_file = goal_dir / f"evidence-{phase.phase_id.lower()}.json"
    evidence = Evidence(
        changed_files=[],
        checks_run=checks,
        verifications=[
            Verification(
                covers="<an acceptance criterion verbatim, or an assumption id like A-1234>",
                kind="auto",
                command="<a command that exits non-zero if this is wrong>",
            )
        ],
        acceptance_met=[],
        known_gaps=[],
        source_ids=[],
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
        memory_suggestions=memory_suggestions,
        evidence_file=str(evidence_file),
        evidence_template=evidence,
        prompt="",
    )
    return plan.model_copy(update={"prompt": render_mode_a_prompt(snapshot, plan, full=full)})


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
    checks.extend(
        [
            "goals brief",
            "goals checkpoint current",
            "goals architecture check --strict",
            "goals merge-check",
            "goals source freshness --strict",
            "goals validate",
        ]
    )
    return checks


def render_mode_a_prompt(snapshot: GoalSnapshot, plan: ModeAPlan, *, full: bool = True) -> str:
    adapter_notes = _adapter_notes(plan.adapter, plan.adapter_ready, plan.adapter_detail)
    criteria = _bullets(plan.acceptance_criteria)
    evidence_json = json.dumps(plan.evidence_template.model_dump(mode="json"), indent=2)
    if not full:
        return _render_short_prompt(snapshot, plan, criteria, evidence_json, adapter_notes)
    checks = _bullets(plan.recommended_checks)
    memory = render_memory_suggestions(plan.memory_suggestions)
    personalization = _personalization_for_prompt()
    sources = render_source_summary(snapshot)
    claims = render_claim_summary(snapshot)
    return f"""/goal Finish this Goals-managed task: {snapshot.objective}

Mode A adapter: {plan.adapter}
Adapter status: {"ready" if plan.adapter_ready else "not confirmed"} - {plan.adapter_detail}

State files:
- Goal snapshot: `{plan.goal_file}`
- Dashboard: `{plan.dashboard_file}`
- Architecture map: `{plan.architecture_file}`
- Evidence draft: `{plan.evidence_file}`
- Portable spec: `{snapshot.topology.worktree_path}/.goals/GOAL.md` (+ `goal-state.json`)

Current phase: {plan.current_phase} - {plan.phase_title}
Phase goal: {plan.phase_goal}

Acceptance criteria:
{criteria}

Required loop:
1. Read `goal.json` before each turn and work only on the current phase.
2. Assess before building: break this phase into sub-problems and hunt the assumptions your approach depends on. Record each with `goals assess assume "I'm assuming X" --building "..." --toward "the sub-problem it serves" [--depends] --phase {plan.current_phase}`, and record the breakdown with `goals assess breakdown --file <breakdown.json>`. Write each assumption plainly enough for a non-technical reader — it becomes the building journey on the dashboard. Skip only for a trivial phase.
3. Make reversible progress without changing unrelated files.
4. Keep `architecture.md` current when the phase changes what is built, planned, blocked, or deferred.
5. Prove it by execution, not by description. First **invert** — deliberately try to break what you built before trusting it: enumerate how it could fail across the dimensions it's exposed to (boundaries and signs, time and locale, empty and huge inputs, concurrency, and the things it depends on — storage, the network, the clock — failing). The gate only makes you defend the assumptions you *name*, so this is where you surface the hidden ones: for each plausible failure, either fix it, write a check that exercises it, or — if it's a premise you're silently relying on — record it as a load-bearing assumption (which then needs its own falsifier). Then, for every acceptance criterion AND every load-bearing assumption, write a **runnable** check that fails if the thing were wrong; a check that cannot fail proves nothing, so make each one actually exercise the failure it guards. Prefer automated checks; a `manual` check is only for the genuinely non-automatable and must say why. Each verification's `covers` is the criterion text or the assumption id (e.g. `A-1234`). Put this in the evidence `verifications` list at `{plan.evidence_file}`.
6. Run `goals phase evidence {plan.current_phase} --file {plan.evidence_file}`, then `goals phase verify {plan.current_phase}` — the engine runs your checks and records the real results; you cannot mark a check passed yourself. Fix the build until every automated check passes.
7. Run `goals issues` to find blockers, missing proof, unresolved source claims, or important user decisions before review.
8. Run `goals brief` before interrupting the user; use its plain wording for any user-facing question.
9. If `goals brief` says `Waiting on: you`, or `goals issues` lists anything under `Needs The User`, ask exactly one plain-language question using the brief wording, then stop. Do not run review or accept until the user answers and the answer is recorded.
10. Run `goals checkpoint current` to confirm the current checkpoint, unresolved proof, and next safe step.
11. Run `goals architecture check --strict` to catch changed code files missing from the architecture map or stale architecture evidence.
12. Run `goals merge-check` to catch migration ordering, branch drift, or parallel-worktree merge risks before acceptance.
13. Run `goals phase review {plan.current_phase}`.
14. Only after the review passes, run `goals phase accept {plan.current_phase}`.
15. Run `goals run --adapter {plan.adapter}` before moving to the next phase.

Parallel worktree merge gate:
- `goals merge-check` scans sibling worktrees when Git exposes them, then reports dirty worktrees, branch drift, file overlap, and migration-ordering risk as agent repair actions unless an explicit high-risk user approval is missing.

Recommended checks for this repo:
{checks}

Skills:
- Run `goals skills list` to see skills discovered live in `~/.claude/skills` and `~/.codex/skills` (plus goals' own bundled skills). Use the ones that fit this phase.

Permission policy:
- Before using an external service, connector, paid tool, production-affecting action, or destructive command, run `goals permission check NAME --kind plugin --action "plain-language action"`.
- If the permission report says `agent_decide`, proceed with a reversible local action and record evidence. If it says `ask_user`, use `goals brief` wording before asking. If it says `deny`, stop and choose a safer local alternative unless the user explicitly approves.

Self-evolution memory:
{memory}
- To reuse lessons from a similar Goals project, run `goals memory sync PATH` first. It is a dry run by default and imports sanitized suggestions only with `--apply`.

User personalization:
{personalization}
- Current explicit user instructions override user memory.
- User memory can guide wording, recommendations, and reversible low-risk choices only; it must not bypass permission policy or high-risk approvals.

Source evidence:
{sources}

Source-backed claims:
{claims}

If this phase makes research, business, customer, market, architecture, migration, or safety claims, record sources with `goals source add "Source title" --locator "url-or-file" --claim "claim supported by this source" --confidence 0.8`.

Before relying on source-backed claims, run `goals source freshness --strict`; add missing locators or summaries, fix missing source ids, refresh, replace, or mark stale sources before asking the user unless a report says the user must decide.

Evidence JSON shape:
```json
{evidence_json}
```

{adapter_notes}

If you hit repeated friction, record it with `goals memory record "what happened" --area phase --kind friction` so future runs can improve phases, skills, gates, or docs.

Portable handoff (works across agents):
- Run `goals export` to refresh `.goals/GOAL.md` and `.goals/goal-state.json`. These are sanitized of local paths and safe to commit so any agent (Claude Code, Codex, Cursor) can resume this goal.
- Run `goals context sync` to keep this goal's managed block current in `AGENTS.md` and `CLAUDE.md` without touching human-authored content.
- Run `goals emit --agent {plan.adapter}` to get a transcript-verifiable native stop-condition derived from this phase's acceptance criteria.

Goals is the durable state and review layer. The native agent goal loop owns persistence of attention; Goals owns phases, evidence, gates, decisions, learnings, memory, the dashboard, and the portable goal spec other agents can read.
"""


def _render_short_prompt(
    snapshot: GoalSnapshot,
    plan: ModeAPlan,
    criteria: str,
    evidence_json: str,
    adapter_notes: str,
) -> str:
    """The calm default handoff: enough to act, not a 15-step wall.

    Paths are shown relative to the goal worktree, and `goals next --full` reaches
    the complete protocol (gates, permissions, sources, memory, portable handoff).
    """
    worktree = Path(snapshot.topology.worktree_path)
    try:
        evidence_rel = str(Path(plan.evidence_file).relative_to(worktree))
    except ValueError:
        evidence_rel = plan.evidence_file
    phase = plan.current_phase
    return f"""/goal Finish this Goals-managed task: {snapshot.objective}

Current phase: {phase} - {plan.phase_title}
Phase goal: {plan.phase_goal}
Acceptance:
{criteria}

Do this:
1. Assess (PACERS): break this phase into sub-problems and hunt the assumptions \
your approach depends on. Record them with \
`goals assess assume "I'm assuming X" --building "..." --toward "..." [--depends] --phase {phase}` \
and `goals assess breakdown --problem "..." --subproblem "statement | task | open question"`. \
Write them plainly enough for a non-technical reader — they become the dashboard's building journey.
2. Build only this phase. Keep changes reversible and don't touch unrelated files.
3. Prove it by execution, not description. First **invert** — try to break it: how could it fail \
(boundaries/signs, time/locale, empty/huge, concurrency, storage or network failing)? Fix each, \
guard it with a check, or — if it's a premise you're relying on — record it as a load-bearing \
assumption. Then for each acceptance criterion AND each load-bearing assumption write a runnable \
check that fails if it's wrong (a check that can't fail proves nothing). Put them in the evidence \
`verifications` list at `{evidence_rel}`, then `goals phase evidence {phase} --file {evidence_rel}` \
and `goals phase verify {phase}` (the engine runs them and records real results — you can't pass a \
check yourself). Fix until all pass.
4. Run `goals brief`. If it says `Waiting on: you`, ask one plain-language question in its \
wording and stop. Otherwise continue.
5. Run `goals phase review {phase}`; once it passes, `goals phase accept {phase}`.

Evidence JSON shape:
```json
{evidence_json}
```

Paths above are relative to the goal worktree: {worktree}
For the complete protocol (architecture, merge, permission, source, and memory gates, plus the \
portable cross-agent handoff), run `goals next --full`. For a plain-language status any time, run \
`goals check`.
{adapter_notes}
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
            "- If Claude Code `/insights` is useful, run it interactively and import the useful summary with `goals user import-insights --file -`.\n"
            "- For non-interactive dry runs, use `claude -p --safe-mode` with an explicit tool list and a realistic budget.\n"
            "- If permissions block progress, choose a reversible local action first and record the blocker as evidence.\n"
            f"- Adapter check detail: {detail if detail else ('ready' if ready else 'not confirmed')}"
        )
    return (
        "Codex Mode A notes:\n"
        "- Use the native `/goal` loop when the local Codex goals feature is enabled.\n"
        "- Use `goals user show` and current session notes for user preferences; do not assume a native Codex `/insights` command exists.\n"
        "- Keep the plan updated during substantial work and summarize checks after each phase.\n"
        "- If the Codex goals feature is unavailable, paste this prompt into the current Codex session and keep Goals as the state layer.\n"
        f"- Adapter check detail: {detail if detail else ('ready' if ready else 'not confirmed')}"
    )


def _personalization_for_prompt() -> str:
    try:
        return render_personalization_context(build_personalization_context())
    except GoalsError as exc:
        return f"- User memory unavailable: {exc}"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None recorded."
