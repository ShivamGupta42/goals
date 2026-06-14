from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from goals.adapters import adapter_check
from goals.architecture import (
    analyze_code_architecture,
    architecture_for_snapshot,
    build_architecture_brief,
    render_architecture_check_report,
    render_architecture_brief,
)
from goals.brief import build_goal_brief, render_goal_brief
from goals.checkpoints import build_current_checkpoint_brief, render_current_checkpoint_brief
from goals.decisions import (
    build_decision_brief,
    build_decision_context,
    render_decision_brief,
    render_decision_explanation,
)
from goals.ecosystem import (
    merge_agent_recommendations,
    recommend_ecosystem_tools,
    render_recommendation_merge_report,
    render_recommendations,
)
from goals.issues import analyze_goal_issues, render_issue_report
from goals.memory import (
    absorb_goal_memory,
    append_memory_entry,
    apply_memory_sync,
    derive_memory_suggestions,
    load_memory,
    memory_path,
    plan_memory_sync,
    render_memory_sync_plan,
    render_memory_suggestions,
)
from goals.merge_readiness import analyze_merge_readiness, render_merge_readiness_report
from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.models import (
    AgentRecommendationSet,
    CheckpointKind,
    CheckpointStatus,
    Decision,
    EcosystemRecommendation,
    Event,
    EventType,
    Evidence,
    GateVerdict,
    GoalArchitectureMap,
    Phase,
    PermissionPolicyReport,
    PhaseCheckpoint,
    SelfEvolutionEntry,
    SourceClaim,
    SourceRecord,
    utc_now,
)
from goals.permission_policy import decide_permission, render_permission_report
from goals.registry import validate_registries
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
from goals.sources import (
    analyze_source_freshness,
    render_claim_summary,
    render_source_freshness_report,
    render_source_summary,
)
from goals.portability import (
    CONTEXT_TARGETS,
    emit_native_goal,
    export_goal,
    render_context_sync,
    render_export,
    render_native_goal_emission,
    sync_context_files,
)
from goals.storage import EventStore, GoalsError, atomic_write_text
from goals.workflows import (
    check_workflow,
    next_workflow,
    render_check_workflow,
    render_start_workflow,
    render_view_workflow,
    start_workflow,
    view_workflow,
)

app = typer.Typer(help="Goals helps AI agents finish bigger tasks without losing track.")
adapter_app = typer.Typer(help="Native goal loop adapters.")
architecture_app = typer.Typer(help="Render and record goal architecture maps.")
context_app = typer.Typer(help="Sync the goal into portable AGENTS.md / CLAUDE.md.")
checkpoint_app = typer.Typer(help="Record and inspect phase checkpoints.")
decision_app = typer.Typer(help="Explain decisions with goal history.")
ecosystem_app = typer.Typer(help="Suggest relevant skills and plugins.")
memory_app = typer.Typer(help="Record and inspect self-evolution memory.")
permission_app = typer.Typer(help="Explain whether a tool or action should ask the user.")
phase_app = typer.Typer(help="Agent phase protocol.")
source_app = typer.Typer(help="Record and inspect source evidence.")


def _handle(fn):
    try:
        return fn()
    except GoalsError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command(rich_help_panel="Simple workflow")
def start(
    objective: str,
    agent: ModeAAdapter = typer.Option(
        "auto",
        "--agent",
        "--adapter",
        help="Native agent to prepare instructions for.",
    ),
    autonomy: str = typer.Option("standard", help="careful, standard, fast, or swarm"),
    why: str = typer.Option("", help="Plain-language reason this goal matters."),
    new: Optional[Path] = typer.Option(None, help="Create a new minimal project first."),
) -> None:
    """Start a goal and show the shortest next steps."""

    def run():
        report = start_workflow(
            objective,
            Path.cwd(),
            agent=agent,
            autonomy=autonomy,
            why=why,
            new_project=new,
        )
        typer.echo(render_start_workflow(report))

    _handle(run)


@app.command("next", rich_help_panel="Simple workflow")
def next_command(
    agent: ModeAAdapter = typer.Option(
        "auto",
        "--agent",
        "--adapter",
        help="Native agent to prepare instructions for.",
    ),
) -> None:
    """Refresh goal files and print the next paste-ready agent handoff."""

    def run():
        report = next_workflow(Path.cwd(), agent=agent)
        typer.echo(report.plan.prompt)

    _handle(run)


@app.command(rich_help_panel="Simple workflow")
def check(
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero when the combined check needs attention.",
    ),
) -> None:
    """Run the main read-only goal health checks in one command."""

    def run():
        report = check_workflow(Path.cwd())
        typer.echo(render_check_workflow(report))
        if strict and not report.passed:
            raise typer.Exit(1)

    _handle(run)


@app.command(rich_help_panel="Simple workflow")
def view(
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the dashboard in the default browser.",
    ),
) -> None:
    """Refresh and show the dashboard and architecture file paths."""

    def run():
        report = view_workflow(Path.cwd())
        if open_browser:
            import webbrowser

            webbrowser.open(report.dashboard_path.resolve().as_uri())
        typer.echo(render_view_workflow(report))

    _handle(run)


@app.command(rich_help_panel="Portability")
def export() -> None:
    """Write the portable, committable goal spec to `.goals/`."""

    def run():
        typer.echo(render_export(export_goal(Path.cwd())))

    _handle(run)


@app.command(rich_help_panel="Portability")
def emit(
    agent: str = typer.Option(
        "claude",
        "--agent",
        "--adapter",
        help="Native agent to emit a stop-condition for: claude or codex.",
    ),
) -> None:
    """Emit a native `/goal` stop-condition from the current phase's acceptance."""

    def run():
        if agent not in ("claude", "codex"):
            raise GoalsError("--agent must be 'claude' or 'codex'.")
        typer.echo(render_native_goal_emission(emit_native_goal(Path.cwd(), agent)))

    _handle(run)


@context_app.command("sync")
def context_sync(
    target: str = typer.Option(
        "both",
        help="Which files to sync: agents, claude, or both.",
    ),
) -> None:
    """Sync the active goal into AGENTS.md and/or CLAUDE.md managed blocks."""

    def run():
        mapping = {
            "agents": ("AGENTS.md",),
            "claude": ("CLAUDE.md",),
            "both": CONTEXT_TARGETS,
        }
        if target not in mapping:
            raise GoalsError("--target must be 'agents', 'claude', or 'both'.")
        typer.echo(render_context_sync(sync_context_files(Path.cwd(), targets=mapping[target])))

    _handle(run)


app.add_typer(adapter_app, name="adapter", rich_help_panel="Advanced building blocks")
app.add_typer(architecture_app, name="architecture", rich_help_panel="Advanced building blocks")
app.add_typer(checkpoint_app, name="checkpoint", rich_help_panel="Advanced building blocks")
app.add_typer(context_app, name="context", rich_help_panel="Portability")
app.add_typer(decision_app, name="decision", rich_help_panel="Advanced building blocks")
app.add_typer(ecosystem_app, name="ecosystem", rich_help_panel="Advanced building blocks")
app.add_typer(memory_app, name="memory", rich_help_panel="Advanced building blocks")
app.add_typer(permission_app, name="permission", rich_help_panel="Advanced building blocks")
app.add_typer(phase_app, name="phase", rich_help_panel="Advanced building blocks")
app.add_typer(source_app, name="source", rich_help_panel="Advanced building blocks")


@app.command(rich_help_panel="Advanced building blocks")
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


@app.command(rich_help_panel="Advanced building blocks")
def status() -> None:
    """Show the active goal status."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        typer.echo(f"Goal: {snapshot.objective}")
        typer.echo(f"Status: {snapshot.status}")
        typer.echo(f"Current phase: {snapshot.current_phase or 'none'}")
        typer.echo(f"Events: {snapshot.event_count}")

    _handle(run)


@app.command(rich_help_panel="Advanced building blocks")
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


@app.command(rich_help_panel="Advanced building blocks")
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


@app.command("merge-check", rich_help_panel="Advanced building blocks")
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


@app.command(rich_help_panel="Advanced building blocks")
def dashboard() -> None:
    """Regenerate the active goal dashboard."""

    def run():
        typer.echo(str(emit_dashboard(Path.cwd())))

    _handle(run)


@checkpoint_app.command("current")
def checkpoint_current(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show the current checkpoint in plain language."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        brief = build_current_checkpoint_brief(snapshot)
        if json_output:
            typer.echo(brief.model_dump_json(indent=2))
        else:
            typer.echo(render_current_checkpoint_brief(brief))

    _handle(run)


@checkpoint_app.command("list")
def checkpoint_list() -> None:
    """List recorded phase checkpoints."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        lines = ["# Phase Checkpoints", ""]
        found = False
        for phase in snapshot.phases:
            if not phase.checkpoints:
                continue
            found = True
            lines.append(f"## {phase.phase_id} - {phase.title}")
            for checkpoint in phase.checkpoints:
                required = "required" if checkpoint.required else "optional"
                user = " user" if checkpoint.needs_user else ""
                lines.append(
                    f"- [{checkpoint.status}][{checkpoint.kind}][{required}{user}] "
                    f"{checkpoint.checkpoint_id}: {checkpoint.title}"
                )
                if checkpoint.summary:
                    lines.append(f"  Summary: {checkpoint.summary}")
                if checkpoint.evidence_refs:
                    lines.append(f"  Evidence: {', '.join(checkpoint.evidence_refs)}")
        if not found:
            lines.append("- No checkpoints recorded.")
        typer.echo("\n".join(lines) + "\n")

    _handle(run)


@checkpoint_app.command("record")
def checkpoint_record(
    phase_id: str,
    checkpoint_id: str,
    title: str = typer.Option("", "--title", help="Plain-language checkpoint title."),
    kind: CheckpointKind = typer.Option(CheckpointKind.CUSTOM, "--kind", help="Checkpoint kind."),
    status: CheckpointStatus = typer.Option(
        CheckpointStatus.PASSED, "--status", help="pending, passed, blocked, needs_user, or waived."
    ),
    required: bool = typer.Option(
        True, "--required/--optional", help="Whether this checkpoint blocks acceptance."
    ),
    needs_user: bool = typer.Option(
        False,
        "--needs-user/--agent-can-complete",
        help="Whether this checkpoint needs a user answer.",
    ),
    summary: str = typer.Option("", "--summary", help="Plain-language checkpoint summary."),
    evidence_refs: Optional[list[str]] = typer.Option(
        None, "--evidence-ref", help="Evidence reference. Repeat for multiple refs."
    ),
    decision_refs: Optional[list[str]] = typer.Option(
        None, "--decision-ref", help="Decision reference. Repeat for multiple refs."
    ),
    notes: str = typer.Option("", "--notes", help="What changed or why this checkpoint exists."),
) -> None:
    """Record or update a phase checkpoint."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        phase = _phase_or_error(snapshot, phase_id)
        existing = _checkpoint_or_none(phase, checkpoint_id)
        checkpoint = PhaseCheckpoint(
            checkpoint_id=checkpoint_id,
            kind=kind,
            title=title or (existing.title if existing else checkpoint_id),
            status=status,
            required=required,
            needs_user=needs_user or status == CheckpointStatus.NEEDS_USER,
            summary=summary or (existing.summary if existing else ""),
            evidence_refs=evidence_refs
            if evidence_refs is not None
            else (existing.evidence_refs if existing else []),
            decision_refs=decision_refs
            if decision_refs is not None
            else (existing.decision_refs if existing else []),
            created_at=existing.created_at if existing else utc_now(),
            updated_at=utc_now(),
            notes=notes or (existing.notes if existing else ""),
        )
        append_event(
            Path.cwd(),
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.PHASE_CHECKPOINT_RECORDED,
                payload={"phase_id": phase_id, "checkpoint": checkpoint.model_dump()},
            ),
        )
        typer.echo(f"Recorded checkpoint {checkpoint_id} for {phase_id}")

    _handle(run)


@checkpoint_app.command("waive")
def checkpoint_waive(
    phase_id: str,
    checkpoint_id: str,
    reason: str = typer.Option(..., "--reason", help="Why it is safe to waive this checkpoint."),
) -> None:
    """Waive an existing required checkpoint with a reason."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        phase = _phase_or_error(snapshot, phase_id)
        existing = _checkpoint_or_none(phase, checkpoint_id)
        if existing is None:
            raise GoalsError(f"Unknown checkpoint id for {phase_id}: {checkpoint_id}")
        checkpoint = existing.model_copy(
            update={
                "status": CheckpointStatus.WAIVED,
                "needs_user": False,
                "summary": reason,
                "updated_at": utc_now(),
                "notes": reason,
            }
        )
        append_event(
            Path.cwd(),
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.PHASE_CHECKPOINT_RECORDED,
                payload={"phase_id": phase_id, "checkpoint": checkpoint.model_dump()},
            ),
        )
        typer.echo(f"Waived checkpoint {checkpoint_id} for {phase_id}")

    _handle(run)


@app.command(rich_help_panel="Advanced building blocks")
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


@app.command(rich_help_panel="Advanced building blocks")
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


@app.command(rich_help_panel="Advanced building blocks")
def doctor() -> None:
    """Inspect the active goal for common state/worktree problems."""

    def run():
        claim_worktree(Path.cwd())
        typer.echo("Doctor check passed.")

    _handle(run)


@app.command(rich_help_panel="Advanced building blocks")
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


@app.command(rich_help_panel="Advanced building blocks")
def cleanup() -> None:
    """Report cleanup candidates. V1 is conservative and does not delete worktrees."""
    typer.echo("Cleanup is report-only in v1. Remove goal worktrees manually after review.")


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


@architecture_app.command("check")
def architecture_check(
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero when architecture/code issues are found.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check whether architecture notes match changed files and code surfaces."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        report = analyze_code_architecture(snapshot, Path.cwd())
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_architecture_check_report(report))
        if strict and not report.passed:
            raise typer.Exit(1)

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


@memory_app.command("sync")
def memory_sync(
    source: Path = typer.Argument(
        ...,
        help="Another Goals project root or .agent-workflow/self-evolution/memory.json file.",
    ),
    apply_changes: bool = typer.Option(
        False,
        "--apply",
        help="Import sanitized suggestions into this project's local memory.",
    ),
    include_private: bool = typer.Option(
        False,
        "--include-private",
        help="Include source summaries and evidence refs. Off by default for privacy.",
    ),
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum suggestions to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Plan or apply sanitized memory imports from another Goals project."""

    def run():
        snapshot = _optional_snapshot(Path.cwd())
        plan = plan_memory_sync(
            Path.cwd(),
            source,
            snapshot,
            include_private=include_private,
            limit=limit,
        )
        result = apply_memory_sync(Path.cwd(), plan, snapshot) if apply_changes else plan
        if json_output:
            typer.echo(result.model_dump_json(indent=2))
        else:
            typer.echo(render_memory_sync_plan(result))

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
    added_at: Optional[str] = typer.Option(
        None,
        "--added-at",
        help="Optional ISO-8601 timestamp for when the source was collected.",
    ),
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
            **({"added_at": added_at} if added_at else {}),
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


@source_app.command("freshness")
def source_freshness(
    max_age_days: Optional[int] = typer.Option(
        None,
        "--max-age-days",
        help="Override the default freshness window for every source.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero when stale or unverifiable sources are found.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check whether recorded sources are fresh enough to rely on."""

    def run():
        if max_age_days is not None and max_age_days < 1:
            raise GoalsError("max-age-days must be greater than 0.")
        snapshot = load_active_snapshot(Path.cwd())
        report = analyze_source_freshness(snapshot, max_age_days=max_age_days)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_source_freshness_report(report))
        if strict and not report.passed:
            raise typer.Exit(1)

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


def _phase_or_error(snapshot, phase_id: str) -> Phase:
    for phase in snapshot.phases:
        if phase.phase_id == phase_id:
            return phase
    raise GoalsError(f"Unknown phase id: {phase_id}")


def _checkpoint_or_none(phase: Phase, checkpoint_id: str) -> PhaseCheckpoint | None:
    for checkpoint in phase.checkpoints:
        if checkpoint.checkpoint_id == checkpoint_id:
            return checkpoint
    return None


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
