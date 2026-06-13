from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from goals.adapters import adapter_check
from goals.architecture import (
    architecture_for_snapshot,
    build_architecture_brief,
    render_architecture_brief,
)
from goals.brief import build_goal_brief, render_goal_brief
from goals.decisions import (
    build_decision_brief,
    build_decision_context,
    render_decision_brief,
    render_decision_explanation,
)
from goals.discovery import discover_local_ecosystem, render_discovery_report
from goals.ecosystem import (
    merge_agent_recommendations,
    recommend_ecosystem_tools,
    render_recommendation_merge_report,
    render_recommendations,
)
from goals.ecosystem_quality import audit_ecosystem_quality, render_ecosystem_quality_report
from goals.evaluations import (
    dogfood_goal_scenarios,
    evaluate_goal_scenarios,
    evaluate_use_case_coverage,
    rehearse_goal_lifecycles,
    render_coverage_report,
    render_dogfood_report,
    render_issue_stress_report,
    render_rehearsal_report,
    render_self_check_report,
    run_self_check,
    stress_goal_issue_discovery,
)
from goals.issues import analyze_goal_issues, render_issue_report
from goals.memory import (
    absorb_goal_memory,
    append_memory_entry,
    derive_memory_suggestions,
    load_memory,
    memory_path,
    render_memory_suggestions,
)
from goals.merge_readiness import analyze_merge_readiness, render_merge_readiness_report
from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.models import (
    AgentRecommendationSet,
    Decision,
    EcosystemRecommendation,
    Event,
    EventType,
    Evidence,
    GateVerdict,
    GoalArchitectureMap,
    PermissionPolicyReport,
    SelfEvolutionEntry,
    SourceClaim,
    SourceRecord,
)
from goals.permission_policy import decide_permission, render_permission_report
from goals.registry import validate_registries
from goals.registry_sync import apply_registry_sync, plan_registry_sync, render_registry_sync_plan
from goals.roadmap import apply_roadmap_update, plan_roadmap_update, render_roadmap_update_plan
from goals.runtime import (
    append_event,
    claim_worktree,
    create_goal,
    emit_architecture,
    emit_dashboard,
    load_active_snapshot,
    run_gate,
    transition_phase,
)
from goals.scanners import run_safety_scanners
from goals.sources import render_claim_summary, render_source_summary
from goals.storage import EventStore, GoalsError, atomic_write_text

app = typer.Typer(help="Goals helps AI agents finish bigger tasks without losing track.")
adapter_app = typer.Typer(help="Native goal loop adapters.")
architecture_app = typer.Typer(help="Render and record goal architecture maps.")
decision_app = typer.Typer(help="Explain decisions with goal history.")
ecosystem_app = typer.Typer(help="Suggest relevant skills and plugins.")
eval_app = typer.Typer(help="Evaluate Goals use-case coverage.")
memory_app = typer.Typer(help="Record and inspect self-evolution memory.")
permission_app = typer.Typer(help="Explain whether a tool or action should ask the user.")
phase_app = typer.Typer(help="Agent phase protocol.")
roadmap_app = typer.Typer(help="Plan self-evolution roadmap updates.")
source_app = typer.Typer(help="Record and inspect source evidence.")
app.add_typer(adapter_app, name="adapter")
app.add_typer(architecture_app, name="architecture")
app.add_typer(decision_app, name="decision")
app.add_typer(ecosystem_app, name="ecosystem")
app.add_typer(eval_app, name="eval")
app.add_typer(memory_app, name="memory")
app.add_typer(permission_app, name="permission")
app.add_typer(phase_app, name="phase")
app.add_typer(roadmap_app, name="roadmap")
app.add_typer(source_app, name="source")


def _handle(fn):
    try:
        return fn()
    except GoalsError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command()
def create(
    objective: str,
    autonomy: str = typer.Option("standard", help="careful, standard, fast, or swarm"),
    why: str = typer.Option("", help="Plain-language reason this goal matters."),
    adapter: ModeAAdapter = typer.Option(
        "auto", help="Native agent adapter to generate instructions for."
    ),
    new: Optional[Path] = typer.Option(None, help="Create a new minimal project first."),
) -> None:
    """Create a goal worktree and initial file-backed state."""

    def run():
        snapshot = create_goal(objective, Path.cwd(), autonomy=autonomy, why=why, new_project=new)
        emit_dashboard(Path(snapshot.topology.worktree_path))
        plan = build_mode_a_plan(snapshot, adapter)
        typer.echo(f"Created goal: {snapshot.goal_id}")
        typer.echo(f"Worktree: {snapshot.topology.worktree_path}")
        typer.echo(
            f"Adapter: {plan.adapter} ({'ready' if plan.adapter_ready else 'not confirmed'})"
        )
        typer.echo(plan.prompt)

    _handle(run)


@app.command()
def status() -> None:
    """Show the active goal status."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        typer.echo(f"Goal: {snapshot.objective}")
        typer.echo(f"Status: {snapshot.status}")
        typer.echo(f"Current phase: {snapshot.current_phase or 'none'}")
        typer.echo(f"Events: {snapshot.event_count}")

    _handle(run)


@app.command()
def issues(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero when blocking issues exist."
    ),
) -> None:
    """Report issues that could stop the active goal from succeeding."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        report = analyze_goal_issues(snapshot)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_issue_report(report))
        if strict and not report.passed:
            raise typer.Exit(1)

    _handle(run)


@app.command()
def brief(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show a plain-language brief for the active goal."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        goal_brief = build_goal_brief(snapshot)
        if json_output:
            typer.echo(goal_brief.model_dump_json(indent=2))
        else:
            typer.echo(render_goal_brief(goal_brief))

    _handle(run)


@app.command("merge-check")
def merge_check(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero when blocking merge findings exist."
    ),
) -> None:
    """Report migration, branch, and parallel-worktree risks before merge."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        report = analyze_merge_readiness(snapshot)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_merge_readiness_report(report))
        if strict and not report.passed:
            raise typer.Exit(1)

    _handle(run)


@app.command()
def dashboard() -> None:
    """Regenerate the active goal dashboard."""

    def run():
        typer.echo(str(emit_dashboard(Path.cwd())))

    _handle(run)


@app.command()
def run(
    adapter: ModeAAdapter = typer.Option(
        "auto", help="Native agent adapter to generate instructions for."
    ),
) -> None:
    """Prepare the next native-agent instruction without controlling the agent process."""

    def inner():
        snapshot = load_active_snapshot(Path.cwd())
        typer.echo(build_mode_a_plan(snapshot, adapter).prompt)

    _handle(inner)


@app.command()
def validate() -> None:
    """Validate active goal state and registry files."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        goal_dir = (
            Path(snapshot.topology.worktree_path) / ".agent-workflow" / "goals" / snapshot.goal_id
        )
        store = EventStore(goal_dir)
        derived = store.snapshot()
        if not store.snapshot_path.exists():
            raise GoalsError("Derived snapshot file is missing.")
        stored = type(derived).model_validate_json(store.snapshot_path.read_text(encoding="utf-8"))
        if stored.model_dump(mode="json") != derived.model_dump(mode="json"):
            raise GoalsError("Derived snapshot does not match the event log. Run `goals repair`.")
        registries = validate_registries(Path.cwd())
        typer.echo(f"Validated goal {snapshot.goal_id}; registries={len(registries)}")

    _handle(run)


@app.command()
def doctor() -> None:
    """Inspect the active goal for common state/worktree problems."""

    def run():
        claim_worktree(Path.cwd())
        typer.echo("Doctor check passed.")

    _handle(run)


@app.command()
def repair() -> None:
    """Rebuild the derived goal snapshot from events."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        goal_dir = (
            Path(snapshot.topology.worktree_path) / ".agent-workflow" / "goals" / snapshot.goal_id
        )
        store = EventStore(goal_dir)
        repaired = store.snapshot()
        atomic_write_text(store.snapshot_path, repaired.model_dump_json(indent=2) + "\n")
        typer.echo("Repaired derived snapshot from event log.")

    _handle(run)


@app.command()
def cleanup() -> None:
    """Report cleanup candidates. V1 is conservative and does not delete worktrees."""
    typer.echo("Cleanup is report-only in v1. Remove goal worktrees manually after review.")


@app.command("safety-check")
def safety_check(
    path: Path = typer.Argument(Path.cwd()),
    mode: str = typer.Option(
        "publish", help="local allows generated goal state; publish blocks it."
    ),
) -> None:
    """Run public-safety scanners."""

    if mode not in {"local", "publish"}:
        typer.secho("Error: mode must be local or publish", fg=typer.colors.RED)
        raise typer.Exit(1)
    results = run_safety_scanners(path.resolve(), mode=mode)
    failed = [result for result in results if result.verdict != GateVerdict.PASS]
    for result in results:
        typer.echo(f"{result.scanner}: {result.verdict}")
        for finding in result.findings:
            typer.echo(f"  - {finding}")
    if failed:
        raise typer.Exit(1)


@adapter_app.command("check")
def adapter_check_command(name: str) -> None:
    """Check whether a native goal-loop adapter is available."""
    ok, detail = adapter_check(name)
    typer.echo(f"{name}: {'ok' if ok else 'not ready'} - {detail}")
    if not ok:
        raise typer.Exit(1)


@architecture_app.command("show")
def architecture_show() -> None:
    """Regenerate and print the active goal architecture Markdown path."""

    def run():
        typer.echo(str(emit_architecture(Path.cwd())))

    _handle(run)


@architecture_app.command("brief")
def architecture_brief(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show a compact architecture review brief for the active goal."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        architecture = architecture_for_snapshot(snapshot)
        brief = build_architecture_brief(architecture)
        if json_output:
            typer.echo(brief.model_dump_json(indent=2))
        else:
            typer.echo(render_architecture_brief(brief))

    _handle(run)


@architecture_app.command("update")
def architecture_update(
    file: Path = typer.Option(..., "--file", "-f", help="Read architecture JSON from a file."),
) -> None:
    """Record a project-specific architecture map for the active goal."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        architecture = GoalArchitectureMap.model_validate_json(file.read_text(encoding="utf-8"))
        append_event(
            Path.cwd(),
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.ARCHITECTURE_UPDATED,
                payload={"architecture": architecture.model_dump()},
            ),
        )
        architecture_path = emit_architecture(Path.cwd())
        emit_dashboard(Path.cwd())
        typer.echo(f"Updated architecture map: {architecture_path}")

    _handle(run)


@ecosystem_app.command("recommend")
def ecosystem_recommend(
    limit: int = typer.Option(6, help="Maximum number of recommendations."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Recommend skills/plugins for the active goal phase."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        recommendations = recommend_ecosystem_tools(Path.cwd(), snapshot, limit=limit)
        if json_output:
            typer.echo(
                json.dumps([rec.model_dump(mode="json") for rec in recommendations], indent=2)
            )
        else:
            typer.echo(render_recommendations(recommendations))

    _handle(run)


@ecosystem_app.command("merge")
def ecosystem_merge(
    file: Optional[list[Path]] = typer.Option(
        None,
        "--file",
        "-f",
        help="Agent recommendation JSON file. Repeat for multiple agents.",
    ),
    limit: int = typer.Option(8, help="Maximum merged recommendations."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Merge recommendations from multiple agents into one coordinator view."""

    def run():
        if file:
            recommendation_sets = _load_agent_recommendation_sets(file)
        else:
            snapshot = load_active_snapshot(Path.cwd())
            recommendation_sets = _default_agent_recommendation_sets(Path.cwd(), snapshot, limit)
        report = merge_agent_recommendations(
            recommendation_sets,
            limit=limit,
            worktree=Path.cwd(),
        )
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_recommendation_merge_report(report))

    _handle(run)


@ecosystem_app.command("discover")
def ecosystem_discover(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    skill_root: Optional[list[Path]] = typer.Option(
        None,
        "--skill-root",
        help="Skill root to inspect. Repeat for multiple roots.",
    ),
    plugin_root: Optional[list[Path]] = typer.Option(
        None,
        "--plugin-root",
        help="Plugin root to inspect. Repeat for multiple roots.",
    ),
    max_skills: int = typer.Option(200, help="Maximum number of skills to inspect."),
    max_plugins: int = typer.Option(100, help="Maximum number of plugins to inspect."),
) -> None:
    """Discover local skills/plugins/adapters and suggest portable registry additions."""

    def run():
        report = discover_local_ecosystem(
            Path.cwd(),
            skill_roots=skill_root,
            plugin_roots=plugin_root,
            max_skills=max_skills,
            max_plugins=max_plugins,
        )
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_discovery_report(report))

    _handle(run)


@ecosystem_app.command("sync")
def ecosystem_sync(
    apply: bool = typer.Option(False, "--apply", help="Write proposed registry additions."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
    skill_root: Optional[list[Path]] = typer.Option(
        None,
        "--skill-root",
        help="Skill root to inspect. Repeat for multiple roots.",
    ),
    plugin_root: Optional[list[Path]] = typer.Option(
        None,
        "--plugin-root",
        help="Plugin root to inspect. Repeat for multiple roots.",
    ),
    max_skills: int = typer.Option(200, help="Maximum number of skills to inspect."),
    max_plugins: int = typer.Option(100, help="Maximum number of plugins to inspect."),
) -> None:
    """Plan or apply portable registry additions from local discovery."""

    def run():
        plan = plan_registry_sync(
            Path.cwd(),
            skill_roots=skill_root,
            plugin_roots=plugin_root,
            max_skills=max_skills,
            max_plugins=max_plugins,
        )
        result = apply_registry_sync(Path.cwd(), plan) if apply else plan
        if json_output:
            typer.echo(result.model_dump_json(indent=2))
        else:
            typer.echo(render_registry_sync_plan(result))
            if not apply and result.changes:
                typer.echo("Run again with --apply to update registries after review.")

    _handle(run)


@ecosystem_app.command("audit")
def ecosystem_audit(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Audit skill/plugin registries for routing quality, safety, and validation readiness."""

    def run():
        report = audit_ecosystem_quality(Path.cwd())
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_ecosystem_quality_report(report))
        if not report.passed:
            raise typer.Exit(1)

    _handle(run)


@memory_app.command("record")
def memory_record(
    note: str,
    area: str = typer.Option("other", help="phase, skill, gate, decision, docs, test, etc."),
    kind: str = typer.Option("friction", help="friction, gap, learning, or success."),
    severity: str = typer.Option("medium", help="low, medium, or high."),
    phase: Optional[str] = typer.Option(None, help="Phase id related to the observation."),
    evidence: Optional[list[str]] = typer.Option(None, "--evidence", help="Evidence reference."),
) -> None:
    """Record reusable friction, gaps, learnings, or successes."""

    def run():
        snapshot = _optional_snapshot(Path.cwd())
        entry = SelfEvolutionEntry(
            kind=_validate_choice(kind, {"friction", "gap", "learning", "success"}, "kind"),  # type: ignore[arg-type]
            area=_validate_choice(
                area,
                {
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
                },
                "area",
            ),  # type: ignore[arg-type]
            note=note,
            severity=_validate_choice(severity, {"low", "medium", "high"}, "severity"),  # type: ignore[arg-type]
            goal_id=snapshot.goal_id if snapshot is not None else "",
            phase_id=phase or (snapshot.current_phase if snapshot is not None else None),
            evidence_refs=evidence or [],
        )
        memory = append_memory_entry(Path.cwd(), entry, snapshot)
        suggestions = derive_memory_suggestions(memory)
        typer.echo(f"Recorded memory: {entry.entry_id}")
        visible = [suggestion for suggestion in suggestions if suggestion.user_visible]
        if visible:
            typer.echo(render_memory_suggestions(visible[:3]))

    _handle(run)


@memory_app.command("suggest")
def memory_suggest(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show self-evolution suggestions derived from repeated friction."""

    def run():
        snapshot = _optional_snapshot(Path.cwd())
        memory = load_memory(Path.cwd(), snapshot)
        suggestions = derive_memory_suggestions(memory)
        if json_output:
            typer.echo(json.dumps([item.model_dump(mode="json") for item in suggestions], indent=2))
        else:
            typer.echo(render_memory_suggestions(suggestions))
            typer.echo(f"Memory file: {memory_path(Path.cwd(), snapshot)}")

    _handle(run)


@memory_app.command("absorb")
def memory_absorb() -> None:
    """Absorb active goal gaps, blockers, failed reviews, and learnings into memory."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        entries = absorb_goal_memory(Path.cwd(), snapshot)
        suggestions = derive_memory_suggestions(load_memory(Path.cwd(), snapshot))
        typer.echo(f"Absorbed {len(entries)} new memory entries.")
        visible = [suggestion for suggestion in suggestions if suggestion.user_visible]
        if visible:
            typer.echo(render_memory_suggestions(visible[:5]))

    _handle(run)


@permission_app.command("check")
def permission_check(
    name: str = typer.Argument(..., help="Tool, command, or action being considered."),
    kind: str = typer.Option(
        "command",
        help="skill, plugin, adapter, agent, gate, command, or other.",
    ),
    action: str = typer.Option("", help="Plain-language action being considered."),
    label: str = typer.Option("", help="Optional display label."),
    reason: str = typer.Option("", help="Why the agent wants to use it."),
    command_hint: str = typer.Option("", help="Optional command or usage hint."),
    requires_user_approval: bool = typer.Option(
        False,
        "--requires-user-approval",
        help="Treat existing tool metadata as approval-required when no policy matches.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero when the policy says to ask the user or stop.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check whether a tool or action can stay with the agent."""

    def run():
        subject_kind = _validate_choice(
            kind,
            {"skill", "plugin", "adapter", "agent", "gate", "command", "other"},
            "kind",
        )
        decision = decide_permission(
            Path.cwd(),
            subject_kind=subject_kind,
            subject_name=name,
            action=action,
            label=label,
            reason=reason,
            command_hint=command_hint,
            fallback_needs_user=requires_user_approval,
        )
        report = PermissionPolicyReport(
            summary=(
                f"Checked {decision.subject_kind} {decision.subject_name}: "
                f"{decision.decision} ({decision.risk})."
            ),
            decisions=[decision],
            user_questions=[decision.user_question] if decision.user_question else [],
            agent_actions=[decision.agent_action] if decision.agent_action else [],
        )
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_permission_report(report))
        if strict and (decision.needs_user or decision.unsafe):
            raise typer.Exit(1)

    _handle(run)


@roadmap_app.command("suggest")
def roadmap_suggest(
    apply: bool = typer.Option(False, "--apply", help="Write the generated roadmap block."),
    adapter: str = typer.Option("both", help="claude, codex, or both."),
    path: Path = typer.Option(Path("ROADMAP.md"), help="Roadmap file to update."),
    max_user_decisions: int = typer.Option(
        2,
        help="Maximum important user decisions allowed per synthetic goal.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Turn self-check findings into a bounded roadmap update plan."""

    def run():
        if adapter == "both":
            adapters = ["claude", "codex"]
        elif adapter in {"claude", "codex"}:
            adapters = [adapter]
        else:
            typer.secho("Error: adapter must be claude, codex, or both", fg=typer.colors.RED)
            raise typer.Exit(1)
        plan = plan_roadmap_update(
            Path.cwd(),
            path=path,
            adapters=adapters,
            max_user_decisions=max_user_decisions,
        )
        result = apply_roadmap_update(Path.cwd(), plan) if apply else plan
        if json_output:
            typer.echo(result.model_dump_json(indent=2))
        else:
            typer.echo(render_roadmap_update_plan(result))
            if not apply and result.suggestions:
                typer.echo("Run again with --apply to update the generated roadmap block.")

    _handle(run)


@source_app.command("add")
def source_add(
    title: str,
    locator: str = typer.Option("", help="URL, file name, interview id, or other locator."),
    source_type: str = typer.Option(
        "other", help="url, file, interview, dataset, document, observation, other."
    ),
    summary: str = typer.Option("", help="Short plain-language source summary."),
    credibility: str = typer.Option("medium", help="low, medium, or high."),
    claim: Optional[str] = typer.Option(None, help="Optional claim supported by this source."),
    confidence: float = typer.Option(0.0, help="Confidence for the optional claim."),
) -> None:
    """Record source evidence for research, business, or technical claims."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        source = SourceRecord(
            title=title,
            locator=locator,
            source_type=_validate_choice(
                source_type,
                {"url", "file", "interview", "dataset", "document", "observation", "other"},
                "source_type",
            ),  # type: ignore[arg-type]
            summary=summary,
            credibility=_validate_choice(credibility, {"low", "medium", "high"}, "credibility"),  # type: ignore[arg-type]
        )
        claims = []
        if claim:
            claims.append(
                SourceClaim(
                    claim=claim,
                    source_ids=[source.source_id],
                    confidence=confidence,
                )
            )
        append_event(
            Path.cwd(),
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.SOURCE_RECORDED,
                payload={
                    "source": source.model_dump(),
                    "claims": [item.model_dump() for item in claims],
                },
            ),
        )
        typer.echo(f"Recorded source: {source.source_id}")

    _handle(run)


@source_app.command("list")
def source_list(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """List source evidence and source-backed claims for the active goal."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "sources": [source.model_dump(mode="json") for source in snapshot.sources],
                        "claims": [
                            claim.model_dump(mode="json") for claim in snapshot.source_claims
                        ],
                    },
                    indent=2,
                )
            )
        else:
            typer.echo("Sources:")
            typer.echo(render_source_summary(snapshot))
            typer.echo("Claims:")
            typer.echo(render_claim_summary(snapshot))

    _handle(run)


@eval_app.command("scenarios")
def eval_scenarios(
    adapter: ModeAAdapter = typer.Option("claude", help="Native adapter shape to evaluate."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Evaluate default personal, technical, business, self-evolution, and ecosystem scenarios."""

    results = evaluate_goal_scenarios(Path.cwd(), adapter=adapter)
    if json_output:
        typer.echo(json.dumps([result.model_dump(mode="json") for result in results], indent=2))
    else:
        for result in results:
            verdict = "pass" if result.current_supported else "missing"
            typer.echo(f"{result.scenario_id}: {verdict} - {result.summary}")
            if result.surfaced_decisions:
                typer.echo("  surfaced decisions:")
                for decision in result.surfaced_decisions:
                    typer.echo(f"  - {decision.plain_question}")
            if result.planned_capabilities:
                typer.echo(f"  planned: {', '.join(result.planned_capabilities)}")
            if result.missing_capabilities:
                typer.echo(f"  missing: {', '.join(result.missing_capabilities)}")
    if any(not result.current_supported for result in results):
        raise typer.Exit(1)


@eval_app.command("dogfood")
def eval_dogfood(
    adapter: ModeAAdapter = typer.Option("claude", help="Native adapter shape to evaluate."),
    max_user_decisions: int = typer.Option(
        2,
        help="Maximum important user decisions allowed per synthetic goal.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Dogfood Goals across synthetic personal, technical, business, self-evolution, and ecosystem goals."""

    report = dogfood_goal_scenarios(
        Path.cwd(),
        adapter=adapter,
        max_user_decisions=max_user_decisions,
    )
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_dogfood_report(report))
    if not report.passed:
        raise typer.Exit(1)


@eval_app.command("coverage")
def eval_coverage(
    adapter: ModeAAdapter = typer.Option("claude", help="Native adapter shape to evaluate."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Evaluate representative goal use-case coverage beyond coding tasks."""

    report = evaluate_use_case_coverage(Path.cwd(), adapter=adapter)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_coverage_report(report))
    if not report.passed:
        raise typer.Exit(1)


@eval_app.command("rehearsal")
def eval_rehearsal(
    adapter: ModeAAdapter = typer.Option(
        "claude", help="Native adapter shape to label the rehearsal."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Run temporary end-to-end goal lifecycle rehearsals."""

    report = rehearse_goal_lifecycles(adapter=adapter)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_rehearsal_report(report))
    if not report.passed:
        raise typer.Exit(1)


@eval_app.command("issue-stress")
def eval_issue_stress(
    adapter: ModeAAdapter = typer.Option(
        "claude", help="Native adapter shape to label the stress report."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Stress issue discovery and user-decision filtering with broken goal states."""

    report = stress_goal_issue_discovery(Path.cwd(), adapter=adapter)
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_issue_stress_report(report))
    if not report.passed:
        raise typer.Exit(1)


@eval_app.command("self-check")
def eval_self_check(
    adapter: str = typer.Option("both", help="claude, codex, or both."),
    max_user_decisions: int = typer.Option(
        2,
        help="Maximum important user decisions allowed per synthetic goal.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Run the full self-evolution evaluation matrix and summarize next slices."""

    if adapter == "both":
        adapters = ["claude", "codex"]
    elif adapter in {"claude", "codex"}:
        adapters = [adapter]
    else:
        typer.secho("Error: adapter must be claude, codex, or both", fg=typer.colors.RED)
        raise typer.Exit(1)
    report = run_self_check(
        Path.cwd(),
        adapters=adapters,
        max_user_decisions=max_user_decisions,
    )
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_self_check_report(report))
    if not report.passed:
        raise typer.Exit(1)


@decision_app.command("explain")
def decision_explain(
    file: Path = typer.Option(..., "--file", "-f", help="Read decision JSON from a file."),
    level: str = typer.Option("basic", help="basic, detailed, or technical."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Explain a decision using the active goal history."""

    def run():
        if level not in {"basic", "detailed", "technical"}:
            raise GoalsError("level must be basic, detailed, or technical.")
        snapshot = load_active_snapshot(Path.cwd())
        context = build_decision_context(snapshot)
        decision = Decision.model_validate_json(file.read_text(encoding="utf-8"))
        if not decision.suggested_reply:
            decision.suggested_reply = f"I choose: {decision.recommendation}"
        decision.what_we_know = decision.what_we_know or []
        decision.evidence_refs = decision.evidence_refs or []
        decision.uncertainty = decision.uncertainty or []
        explanation = render_decision_explanation(decision, context, level=level)  # type: ignore[arg-type]
        if json_output:
            typer.echo(explanation.model_dump_json(indent=2))
        else:
            typer.echo(explanation.markdown)
            if not explanation.surfaced_to_user:
                typer.echo("\nAgent note: this does not need to interrupt the user.")

    _handle(run)


@decision_app.command("brief")
def decision_brief(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show the important user decisions in a compact plain-language brief."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        brief = build_decision_brief(snapshot)
        if json_output:
            typer.echo(brief.model_dump_json(indent=2))
        else:
            typer.echo(render_decision_brief(brief))

    _handle(run)


def _optional_snapshot(cwd: Path):
    try:
        return load_active_snapshot(cwd)
    except GoalsError:
        return None


def _default_agent_recommendation_sets(
    cwd: Path, snapshot, limit: int
) -> list[AgentRecommendationSet]:
    recommendations = recommend_ecosystem_tools(cwd, snapshot, limit=limit)
    phase_id = snapshot.current_phase or ""
    return [
        AgentRecommendationSet(
            agent_id="claude",
            adapter="claude",
            phase_id=phase_id,
            recommendations=recommendations,
            notes="Default Claude-shaped Mode A recommendations.",
        ),
        AgentRecommendationSet(
            agent_id="codex",
            adapter="codex",
            phase_id=phase_id,
            recommendations=recommendations,
            notes="Default Codex-shaped Mode A recommendations.",
        ),
    ]


def _load_agent_recommendation_sets(files: list[Path]) -> list[AgentRecommendationSet]:
    loaded: list[AgentRecommendationSet] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded.extend(_agent_recommendation_sets_from_data(data, path.stem))
    if not loaded:
        raise GoalsError("No agent recommendations found.")
    return loaded


def _agent_recommendation_sets_from_data(
    data, default_agent_id: str
) -> list[AgentRecommendationSet]:
    if isinstance(data, dict) and "recommendations" in data:
        return [AgentRecommendationSet.model_validate(data)]
    if isinstance(data, dict) and {"kind", "name"}.issubset(data):
        return [
            AgentRecommendationSet(
                agent_id=default_agent_id,
                recommendations=[EcosystemRecommendation.model_validate(data)],
            )
        ]
    if isinstance(data, list):
        if all(isinstance(item, dict) and "recommendations" in item for item in data):
            return [AgentRecommendationSet.model_validate(item) for item in data]
        return [
            AgentRecommendationSet(
                agent_id=default_agent_id,
                recommendations=[EcosystemRecommendation.model_validate(item) for item in data],
            )
        ]
    raise GoalsError("Recommendation file must contain an agent set or recommendation list.")


def _validate_choice(value: str, choices: set[str], label: str) -> str:
    if value not in choices:
        raise GoalsError(f"{label} must be one of: {', '.join(sorted(choices))}")
    return value


@phase_app.command("start")
def phase_start(phase_id: str) -> None:
    """Record that a phase has started."""

    def run():
        transition_phase(Path.cwd(), phase_id, "start")
        typer.echo(f"Started phase {phase_id}")

    _handle(run)


@phase_app.command("evidence")
def phase_evidence(
    phase_id: str,
    evidence_json: Optional[str] = typer.Argument(None),
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Read evidence JSON from a file."
    ),
) -> None:
    """Record phase evidence from a JSON object."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        if file is not None and evidence_json is not None:
            raise GoalsError("Provide evidence as inline JSON or --file, not both.")
        if file is None and evidence_json is None:
            raise GoalsError("Provide evidence as inline JSON or --file.")
        raw = file.read_text(encoding="utf-8") if file is not None else evidence_json
        evidence = Evidence.model_validate(json.loads(raw or "{}"))
        append_event(
            Path.cwd(),
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.PHASE_EVIDENCE,
                payload={"phase_id": phase_id, "evidence": evidence.model_dump()},
            ),
        )
        typer.echo(f"Recorded evidence for {phase_id}")

    _handle(run)


@phase_app.command("review")
def phase_review(phase_id: str) -> None:
    """Run the typed phase review gate."""

    def run():
        result = run_gate(Path.cwd(), phase_id)
        typer.echo(f"{result.verdict}: {result.summary}")
        if result.verdict != GateVerdict.PASS:
            raise typer.Exit(1)

    _handle(run)


@phase_app.command("accept")
def phase_accept(phase_id: str) -> None:
    """Accept a reviewed phase."""

    def run():
        transition_phase(Path.cwd(), phase_id, "accept")
        typer.echo(f"Accepted phase {phase_id}")

    _handle(run)


if __name__ == "__main__":
    app()
