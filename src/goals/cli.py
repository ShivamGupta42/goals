from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, cast

import typer
from pydantic import ValidationError

from goals.adapters import adapter_check
from goals.agent_hooks import session_start_payload, stop_payload
from goals.architecture import (
    analyze_code_architecture,
    architecture_for_snapshot,
    build_architecture_brief,
    render_architecture_check_report,
    render_architecture_brief,
)
from goals.audit import (
    build_audit_report,
    build_event_lineage,
    build_phase_lineage,
    render_audit_report,
    render_lineage,
)
from goals.brief import build_goal_brief, render_goal_brief
from goals.capabilities import analyze_capabilities, render_capability_report
from goals.checkpoints import render_current_checkpoint_brief
from goals.checkpoint_workflows import (
    current_checkpoint,
    record_checkpoint as record_checkpoint_workflow,
    render_checkpoint_list,
    waive_checkpoint as waive_checkpoint_workflow,
)
from goals.decisions import render_decision_brief
from goals.decision_workflows import (
    decision_brief_workflow,
    explain_decision_workflow,
    record_decision as record_decision_workflow,
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
from goals.loop_builder import (
    load_design,
    new_session,
    profile_root_for_loop_path,
    render_loop_html,
    run_builder,
    run_script,
    save_design,
)
from goals.loop_check import (
    AgentName,
    apply_fixes,
    check_loop,
    render_fix_summary,
    render_loop_check_report,
)
from goals.loop_catalog import import_loop_design, render_import_result
from goals.diagram import render_architecture as render_architecture_diagram
from goals.diagram import render_loop as render_loop_diagram
from goals.loop_improve import (
    apply_loop_improvements,
    log_phase_regression,
    plan_loop_improvements,
    render_loop_improvement_plan,
    render_regression_report,
)
from goals.merge_readiness import analyze_merge_readiness, render_merge_readiness_report
from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.journey import render_journey_text
from goals.models import (
    Assumption,
    CheckpointKind,
    CheckpointStatus,
    Decision,
    Event,
    EventType,
    Evidence,
    GateVerdict,
    GoalArchitectureMap,
    Phase,
    PermissionPolicyReport,
    PhaseCheckpoint,
    ProblemBreakdown,
    SelfEvolutionEntry,
    SourceClaim,
    SourceRecord,
    Subproblem,
    UserMemoryEvent,
    Verification,
)
from goals.permission_policy import decide_permission, render_permission_report
from goals.phase_workflows import (
    accept_phase,
    record_phase_evidence,
    review_phase_workflow,
    start_phase,
    verify_phase_workflow,
)
from goals.registry import validate_registries
from goals.rubric import category_for
from goals.setup import render_setup_report, setup_agents
from goals.simulate import render_simulation_report, run_simulations
from goals.runtime import (
    append_event,
    claim_worktree,
    create_goal,
    emit_architecture,
    emit_dashboard,
    load_active_snapshot,
    resolve_workspace,
)
from goals.skill_capabilities import render_skill_capability_report
from goals.skill_workflows import (
    import_skill,
    install_skills as install_skills_workflow,
    list_skills as list_skills_workflow,
    preflight_skills,
)
from goals.sources import render_claim_summary, render_source_freshness_report, render_source_summary
from goals.source_workflows import (
    record_source,
    source_freshness as source_freshness_workflow,
    source_list as source_list_workflow,
)
from goals.portability import (
    CONTEXT_TARGETS,
    emit_native_goal,
    export_goal,
    render_context_block,
    render_context_sync,
    render_export,
    render_native_goal_emission,
    sync_context_files,
)
from goals.skill_discovery import render_install_report, render_skills_list
from goals.storage import EventStore, GoalsError, atomic_write_text
from goals.tools import render_tool_health_report
from goals.tool_workflows import tool_doctor
from goals.user_memory import (
    INTERVIEW_QUESTIONS,
    append_user_event,
    build_goal_memory_digest,
    build_personalization_context,
    events_from_insights,
    forget_claim,
    load_user_memory,
    record_interview_answers,
    render_user_memory,
)
from goals.workflows import (
    check_workflow,
    finish_workflow,
    next_workflow,
    render_check_workflow,
    render_finish_workflow,
    render_start_workflow,
    render_view_workflow,
    start_workflow,
    view_workflow,
)

app = typer.Typer(help="Goals helps AI agents finish bigger tasks without losing track.")
adapter_app = typer.Typer(help="Native goal loop adapters.")
architecture_app = typer.Typer(help="Render and record goal architecture maps.")
assess_app = typer.Typer(help="Record the building journey — assumptions and problem breakdowns.")
capability_app = typer.Typer(help="Check skill and tool capabilities before work proceeds.")
context_app = typer.Typer(help="Sync the goal into portable AGENTS.md / CLAUDE.md.")
checkpoint_app = typer.Typer(help="Record and inspect phase checkpoints.")
decision_app = typer.Typer(help="Explain decisions with goal history.")
hooks_app = typer.Typer(help="Emit Claude Code plugin hook payloads.")
loop_app = typer.Typer(help="Visually build, check, and improve goal loops.")
memory_app = typer.Typer(help="Record and inspect self-evolution memory.")
permission_app = typer.Typer(help="Explain whether a tool or action should ask the user.")
phase_app = typer.Typer(help="Agent phase protocol.")
skills_app = typer.Typer(help="Discover and install skills from agent dirs.")
source_app = typer.Typer(help="Record and inspect source evidence.")
tools_app = typer.Typer(help="Inspect local tool capability health.")
user_app = typer.Typer(help="Record and inspect private global user memory.")


def _load_json_model(inline: str | None, file: Optional[Path], model):
    """Read inline-or-``--file`` JSON into a model with clean errors.

    CLI args are a user-input boundary: an unreadable ``--file``, malformed JSON,
    or a payload that fails validation must all surface as a plain ``Error: …``,
    not a raw traceback. ``_handle`` only catches ``GoalsError``, so we translate
    ``OSError`` (read), ``JSONDecodeError`` (parse), and pydantic
    ``ValidationError`` (schema) here. The caller still enforces exactly-one-of
    inline/``--file`` so it can word that message naturally.
    """
    if file is not None:
        try:
            raw: str | None = file.read_text(encoding="utf-8")
        except OSError as exc:
            raise GoalsError(f"Could not read {file}: {exc}") from exc
    else:
        raw = inline
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise GoalsError(f"Invalid JSON: {exc}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise GoalsError(_format_validation_error(model, exc)) from exc


def _format_validation_error(model, exc: ValidationError) -> str:
    """Turn a raw pydantic error into an actionable, agent-friendly message.

    The common authoring mistake is an extra key the model forbids (e.g. a
    ``summary`` field on ``Evidence``, or a stray key inside a nested
    ``verifications[i]``). Name the offending keys by their full path and list
    what is allowed, instead of leaving the agent to decode a pydantic
    traceback. Non-"extra" problems (missing/type errors) are summarised too —
    never silently dropped — so a mixed payload surfaces all of its issues.
    """
    extra_paths: list[str] = []
    other: list[str] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        path = ".".join(str(part) for part in loc) or "(root)"
        if err.get("type") == "extra_forbidden":
            extra_paths.append(path)
        else:
            other.append(f"{path}: {err.get('msg', 'invalid')}")
    if not extra_paths and not other:
        return f"Invalid {model.__name__}: {exc}"
    allowed = ", ".join(sorted(model.model_fields)) or "(none)"
    parts: list[str] = []
    if extra_paths:
        parts.append("unknown field(s): " + ", ".join(sorted(set(extra_paths))))
    if other:
        parts.append("other problem(s): " + "; ".join(other))
    return (
        f"Invalid {model.__name__}: "
        + ". ".join(parts)
        + f". Allowed top-level fields: {allowed}."
    )


def _parse_subproblem(spec: str) -> Subproblem:
    """Parse a flag-mode sub-problem: "statement | task1; task2 | q1; q2".

    Only the statement is required; the tasks and open-questions segments are
    optional and each splits on ``;``. Lets a user author a breakdown without
    writing nested JSON.
    """
    parts = [segment.strip() for segment in spec.split("|")]
    statement = parts[0]
    if not statement:
        raise GoalsError("A --subproblem needs a statement before the first '|'.")
    tasks = [t.strip() for t in parts[1].split(";") if t.strip()] if len(parts) > 1 else []
    questions = [q.strip() for q in parts[2].split(";") if q.strip()] if len(parts) > 2 else []
    return Subproblem(statement=statement, tasks=tasks, open_questions=questions)


def _handle(fn):
    try:
        return fn()
    except GoalsError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command(rich_help_panel="Simple workflow")
def start(
    objective: Optional[str] = typer.Argument(None),
    agent: ModeAAdapter = typer.Option(
        "auto",
        "--agent",
        "--adapter",
        help="Native agent to prepare instructions for.",
    ),
    autonomy: str = typer.Option("standard", help="careful, standard, fast, or swarm"),
    why: str = typer.Option("", help="Plain-language reason this goal matters."),
    new: Optional[Path] = typer.Option(None, help="Create a new minimal project first."),
    worktree: bool = typer.Option(
        False, "--worktree", help="Force an isolated worktree (best for several goals at once)."
    ),
    in_place: bool = typer.Option(
        False, "--in-place", help="Work on the current branch (ignored on main/master)."
    ),
    loop: Optional[Path] = typer.Option(
        None, "--loop", help="Start from a saved loop-design.json or .goals directory."
    ),
) -> None:
    """Start a goal and show the shortest next steps."""

    def run():
        if objective is None and loop is None:
            raise GoalsError("Provide an objective or --loop.")
        if worktree and in_place:
            raise GoalsError("Choose either --worktree or --in-place, not both.")
        requested = "worktree" if worktree else "in_place" if in_place else "auto"
        # On a feature branch with no explicit choice, offer the worktree-vs-in-place
        # decision interactively; non-interactive callers (agents) get the safe default.
        if requested == "auto" and new is None and sys.stdin.isatty():
            plan = resolve_workspace(Path.cwd(), requested="auto")
            if plan.ambiguous:
                answer = typer.prompt(
                    f"On branch '{plan.base_branch}'. Work in place (simplest, no cd), "
                    "or isolate this goal in a worktree (for several goals at once)? "
                    "[in-place/worktree]",
                    default="in-place",
                )
                requested = "worktree" if answer.strip().lower().startswith("w") else "in_place"
        report = start_workflow(
            objective or "",
            Path.cwd(),
            agent=agent,
            autonomy=autonomy,
            why=why,
            new_project=new,
            workspace=requested,
            loop=loop,
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
    full: bool = typer.Option(
        False, "--full", help="Print the complete protocol (gates, permissions, sources, memory)."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON (evidence template + allowed fields)."
    ),
) -> None:
    """Refresh goal files and print the next paste-ready agent handoff.

    Prints a short, act-now handoff by default; add ``--full`` for the complete
    protocol with every gate, permission, source, and memory step. Use ``--json``
    to get the exact evidence schema (field names + which keys are allowed)
    before authoring an evidence file.
    """

    def run():
        if json_output:
            # --json is a machine API: a complete goal (no current phase) must
            # return a structured payload, not a plain-text GoalsError.
            try:
                report = next_workflow(Path.cwd(), agent=agent, full=full)
            except GoalsError as exc:
                typer.echo(json.dumps({"current_phase": None, "error": str(exc)}, indent=2))
                return
            payload = {
                "current_phase": report.plan.current_phase,
                "evidence_file": report.plan.evidence_file,
                "evidence_template": report.plan.evidence_template.model_dump(mode="json"),
                "evidence_fields": sorted(Evidence.model_fields),
                "verification_fields": sorted(Verification.model_fields),
                "note": (
                    "Author evidence to these fields only (extra keys are rejected). "
                    "'ran'/'passed' on verifications are engine-owned and set by "
                    "`goals phase verify`."
                ),
            }
            typer.echo(json.dumps(payload, indent=2))
            return
        report = next_workflow(Path.cwd(), agent=agent, full=full)
        typer.echo(report.plan.prompt)

    _handle(run)


@app.command(rich_help_panel="Simple workflow")
def check(
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero when the combined check needs attention.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Refresh the portable `.goals` export while checking.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Run the main read-only goal health checks in one command."""

    def run():
        report = check_workflow(Path.cwd(), refresh=refresh)
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "goal_id": report.snapshot.goal_id,
                        "passed": report.passed,
                        "brief": report.brief.model_dump(mode="json"),
                        "issues": report.issues.model_dump(mode="json"),
                        "checkpoint": (
                            report.checkpoint.model_dump(mode="json")
                            if report.checkpoint
                            else None
                        ),
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(render_check_workflow(report))
        if strict and not report.passed:
            raise typer.Exit(1)

    _handle(run)


@app.command(rich_help_panel="Simple workflow")
def finish(
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Exit non-zero if closeout is not ready."),
) -> None:
    """Run closeout checks and refresh portable state without bypassing phase gates."""

    def run():
        report = finish_workflow(Path.cwd())
        typer.echo(render_finish_workflow(report))
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
app.add_typer(assess_app, name="assess", rich_help_panel="Advanced building blocks")
app.add_typer(capability_app, name="capability", rich_help_panel="Advanced building blocks")
app.add_typer(checkpoint_app, name="checkpoint", rich_help_panel="Advanced building blocks")
app.add_typer(context_app, name="context", rich_help_panel="Portability")
app.add_typer(decision_app, name="decision", rich_help_panel="Advanced building blocks")
app.add_typer(hooks_app, name="hooks", rich_help_panel="Portability")
app.add_typer(loop_app, name="loop", rich_help_panel="Simple workflow")
app.add_typer(memory_app, name="memory", rich_help_panel="Advanced building blocks")
app.add_typer(permission_app, name="permission", rich_help_panel="Advanced building blocks")
app.add_typer(phase_app, name="phase", rich_help_panel="Advanced building blocks")
app.add_typer(skills_app, name="skills", rich_help_panel="Portability")
app.add_typer(source_app, name="source", rich_help_panel="Advanced building blocks")
app.add_typer(tools_app, name="tools", rich_help_panel="Advanced building blocks")
app.add_typer(user_app, name="user", rich_help_panel="Advanced building blocks")


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
def status(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show the active goal status."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "goal_id": snapshot.goal_id,
                        "objective": snapshot.objective,
                        "status": str(snapshot.status),
                        "current_phase": snapshot.current_phase,
                        "event_count": snapshot.event_count,
                    },
                    indent=2,
                )
            )
            return
        typer.echo(f"Goal: {snapshot.objective}")
        typer.echo(f"Status: {snapshot.status}")
        typer.echo(f"Current phase: {snapshot.current_phase or 'none'}")
        typer.echo(f"Events: {snapshot.event_count}")

    _handle(run)


@context_app.command("show")
def context_show(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Print the active goal's context block (for agent session hooks)."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        if not json_output:
            typer.echo(render_context_block(snapshot))
            return
        brief = build_goal_brief(snapshot)
        current = next(
            (p for p in snapshot.phases if p.phase_id == snapshot.current_phase), None
        )
        typer.echo(
            json.dumps(
                {
                    "goal_id": snapshot.goal_id,
                    "objective": snapshot.objective,
                    "status": str(snapshot.status),
                    "current_phase": snapshot.current_phase,
                    "phase_title": current.title if current else None,
                    "acceptance_criteria": list(current.acceptance_criteria) if current else [],
                    "waiting_on": brief.waiting_on,
                    "worktree_path": snapshot.topology.worktree_path,
                    "next_step": brief.current_step,
                },
                indent=2,
            )
        )

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


@capability_app.command("check")
def capability_check(
    agent: str = typer.Option(
        "auto",
        "--agent",
        "--adapter",
        help="Agent inventory to check against: auto, claude, or codex.",
    ),
    need: Optional[list[str]] = typer.Option(
        None,
        "--need",
        help="Explicit capability need, e.g. skill:browser or browser:visual checks.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero when a required capability is missing.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check whether this goal has the skills/tools it appears to need."""

    def run():
        adapter = _validate_choice(agent, {"auto", "claude", "codex"}, "agent")
        snapshot = load_active_snapshot(Path.cwd())
        try:
            report = analyze_capabilities(
                snapshot,
                adapter=adapter,  # type: ignore[arg-type]
                explicit_needs=need or [],
            )
        except ValueError as exc:
            raise GoalsError(str(exc)) from exc
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_capability_report(report))
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
        brief = current_checkpoint(Path.cwd())
        if json_output:
            typer.echo(brief.model_dump_json(indent=2))
        else:
            typer.echo(render_current_checkpoint_brief(brief))

    _handle(run)


@checkpoint_app.command("list")
def checkpoint_list() -> None:
    """List recorded phase checkpoints."""

    def run():
        typer.echo(render_checkpoint_list(load_active_snapshot(Path.cwd())))

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
        record_checkpoint_workflow(
            Path.cwd(),
            phase_id,
            checkpoint_id,
            kind=kind,
            title=title,
            status=status,
            required=required,
            needs_user=needs_user or status == CheckpointStatus.NEEDS_USER,
            summary=summary,
            evidence_refs=evidence_refs,
            decision_refs=decision_refs,
            notes=notes,
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
        waive_checkpoint_workflow(Path.cwd(), phase_id, checkpoint_id, reason)
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
def validate(
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Also fail on dangling causal refs and artifact hash mismatches.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Validate active goal state and registry files."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        goal_dir = (
            Path(snapshot.topology.worktree_path) / ".agent-workflow" / "goals" / snapshot.goal_id
        )
        registries = validate_registries(Path.cwd())
        report = build_audit_report(
            goal_dir,
            worktree=Path(snapshot.topology.worktree_path),
            strict=strict,
            registry_count=len(registries),
        )
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_audit_report(report))
        if not report.passed:
            raise typer.Exit(1)

    _handle(run)


@app.command(rich_help_panel="Advanced building blocks")
def lineage(
    event: Optional[str] = typer.Option(None, "--event", help="Show lineage for an event id."),
    phase: Optional[str] = typer.Option(None, "--phase", help="Show recent lineage for a phase id."),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show why an event or phase exists by walking causal event links."""

    def run():
        if bool(event) == bool(phase):
            raise GoalsError("Provide exactly one of --event or --phase.")
        snapshot = load_active_snapshot(Path.cwd())
        goal_dir = (
            Path(snapshot.topology.worktree_path) / ".agent-workflow" / "goals" / snapshot.goal_id
        )
        events = EventStore(goal_dir).read_events()
        result = build_event_lineage(events, event) if event else build_phase_lineage(events, phase or "")
        if json_output:
            typer.echo(result.model_dump_json(indent=2))
        else:
            typer.echo(render_lineage(result))

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


@app.command(rich_help_panel="Advanced building blocks")
def simulate(
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero when a simulation scenario fails."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Run disposable workflow simulations for regression coverage."""

    report = run_simulations()
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(render_simulation_report(report))
    if strict and not report.passed:
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
        architecture = _load_json_model(None, file, GoalArchitectureMap)
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


@user_app.command("show")
def user_show(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show private global user memory."""

    def run():
        memory = load_user_memory()
        if json_output:
            typer.echo(memory.model_dump_json(indent=2))
        else:
            typer.echo(render_user_memory(memory))

    _handle(run)


@user_app.command("digest")
def user_digest(
    goal: str = typer.Option("current", "--goal", help="'current' or a goal id."),
) -> None:
    """Surface what Goals learned for goal execution, the way it does at goal end."""

    def run():
        goal_id = _resolve_user_goal_id(goal)
        digest = build_goal_memory_digest(goal_id)
        typer.echo(digest.rstrip() if digest else "No goal-execution memory recorded yet.")

    _handle(run)


@user_app.command("record")
def user_record(
    preference: str,
    area: str = typer.Option(
        "decision",
        help="risk, communication, workflow, technical, decision, or other.",
    ),
    confidence: float = typer.Option(0.95, "--confidence", min=0.0, max=1.0),
) -> None:
    """Record an explicit user preference in private global memory."""

    def run():
        event = UserMemoryEvent(
            kind="manual",
            area=_user_area(area),  # type: ignore[arg-type]
            summary=preference,
            source="manual",
            confidence=confidence,
        )
        memory = append_user_event(event)
        typer.echo(f"Recorded user memory event: {event.event_id}")
        active = [claim for claim in memory.claims if claim.status == "active"]
        if active:
            typer.echo(render_user_memory(memory))

    _handle(run)


@user_app.command("import-insights")
def user_import_insights(
    file: Path = typer.Option(..., "--file", "-f", help="Read Claude /insights text from a file, or '-' for stdin."),
    area: str = typer.Option(
        "decision",
        help="risk, communication, workflow, technical, decision, or other.",
    ),
) -> None:
    """Import a Claude Code /insights summary as candidate user memory."""

    def run():
        if str(file) == "-":
            text = sys.stdin.read()
        else:
            try:
                text = file.read_text(encoding="utf-8")
            except OSError as exc:
                raise GoalsError(f"Could not read {file}: {exc}") from exc
        events = events_from_insights(text, area=_user_area(area))  # type: ignore[arg-type]
        if not events:
            raise GoalsError("No usable insight statements found.")
        memory = None
        for event in events:
            memory = append_user_event(event)
        typer.echo(f"Imported {len(events)} user memory candidate(s) from Claude insights.")
        if memory is not None:
            typer.echo(render_user_memory(memory))

    _handle(run)


@user_app.command("interview")
def user_interview(
    goal: str = typer.Option("current", "--goal", help="'current' or a goal id."),
    answers: Optional[list[str]] = typer.Option(
        None,
        "--answer",
        "-a",
        help="Interview answer. Repeat exactly three times.",
    ),
) -> None:
    """Record the three-question post-goal personalization interview."""

    def run():
        goal_id = _resolve_user_goal_id(goal)
        collected = list(answers or [])
        if not collected and sys.stdin.isatty():
            collected = [typer.prompt(question) for question in INTERVIEW_QUESTIONS]
        event = record_interview_answers(goal_id, collected)
        memory = append_user_event(event)
        typer.echo(f"Recorded post-goal user interview: {event.event_id}")
        typer.echo(render_user_memory(memory))

    _handle(run)


@user_app.command("forget")
def user_forget(
    claim_id: Optional[str] = typer.Argument(None, help="Claim id to forget."),
    all_claims: bool = typer.Option(False, "--all", help="Forget all user-memory claims."),
    purge: bool = typer.Option(False, "--purge", help="Delete user memory files when used with --all."),
) -> None:
    """Deactivate or purge private user-memory claims."""

    def run():
        if all_claims:
            memory = forget_claim("--all", purge=purge)
            typer.echo("Forgot all user-memory claims." if not purge else "Purged user memory.")
            if not purge:
                typer.echo(render_user_memory(memory))
            return
        if not claim_id:
            raise GoalsError("Provide a claim id, or use --all.")
        memory = forget_claim(claim_id)
        typer.echo(f"Forgot user-memory claim: {claim_id}")
        typer.echo(render_user_memory(memory))

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
        record_source(Path.cwd(), source, claims=claims)
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
        report = source_freshness_workflow(Path.cwd(), max_age_days=max_age_days)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_source_freshness_report(report))
        if strict and not report.passed:
            raise typer.Exit(1)

    _handle(run)


@tools_app.command("doctor")
def tools_doctor(
    record: bool = typer.Option(
        False,
        "--record",
        help="Record the tool health snapshot in the active goal.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero when no usable native or browser capability is found.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check native-agent and browser/tool capability health."""

    def run():
        report = tool_doctor(Path.cwd(), record=record)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_tool_health_report(report))
        if strict and not report.passed:
            raise typer.Exit(1)

    _handle(run)


@source_app.command("list")
def source_list(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """List source evidence and source-backed claims for the active goal."""

    def run():
        report = source_list_workflow(Path.cwd())
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "sources": [source.model_dump(mode="json") for source in report.sources],
                        "claims": [claim.model_dump(mode="json") for claim in report.claims],
                    },
                    indent=2,
                )
            )
        else:
            snapshot = load_active_snapshot(Path.cwd())
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
        decision = _load_json_model(None, file, Decision)
        explanation = explain_decision_workflow(
            Path.cwd(),
            decision,
            level=level,  # type: ignore[arg-type]
            personalization=_personalization_or_none(),
        )
        if json_output:
            typer.echo(explanation.model_dump_json(indent=2))
        else:
            typer.echo(explanation.markdown)
            if not explanation.surfaced_to_user:
                typer.echo("\nAgent note: this does not need to interrupt the user.")

    _handle(run)


@decision_app.command("record")
def decision_record(
    question: str = typer.Argument(..., help="The question or choice that was decided."),
    choice: str = typer.Option(..., "--choice", help="What was chosen."),
    why: str = typer.Option("", "--why", help="Why this choice was made."),
    by: str = typer.Option("user", "--by", help="Who decided: user or agent."),
    reversible: bool = typer.Option(
        True, "--reversible/--irreversible", help="Whether the choice can be undone."
    ),
    phase: Optional[str] = typer.Option(
        None, "--phase", help="Phase this decision belongs to (e.g. P2)."
    ),
    evidence: Optional[list[str]] = typer.Option(
        None, "--evidence", help="Evidence reference. Repeat for multiple refs."
    ),
    profile_claim: Optional[list[str]] = typer.Option(
        None, "--profile-claim", help="User-memory claim id used for this decision."
    ),
    confidence: float = typer.Option(0.0, "--confidence", min=0.0, max=1.0),
) -> None:
    """Record a decision the user (or agent) made, building the judgement log.

    Decisions happen in the agent conversation, not on the read-only dashboard.
    Call this when a judgement is made so the dashboard can show what was decided
    and why — the durable history behind the goal.
    """

    def run():
        report = record_decision_workflow(
            Path.cwd(),
            question=question,
            choice=choice,
            decided_by=_validate_choice(by, {"user", "agent"}, "by"),  # type: ignore[arg-type]
            why=why,
            reversible=reversible,
            phase_id=phase,
            evidence_refs=evidence or [],
            profile_claim_ids=profile_claim or [],
            confidence=confidence,
        )
        if report.warning:
            typer.echo(report.warning, err=True)
        typer.echo(f"Recorded decision: {report.record.judgement_id}")

    _handle(run)


@decision_app.command("brief")
def decision_brief(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show the important user decisions in a compact plain-language brief."""

    def run():
        brief = decision_brief_workflow(Path.cwd(), _personalization_or_none())
        if json_output:
            typer.echo(brief.model_dump_json(indent=2))
        else:
            typer.echo(render_decision_brief(brief))

    _handle(run)


@assess_app.command("assume")
def assess_assume(
    statement: str = typer.Argument(..., help="Plain-English assumption: 'I'm assuming X'."),
    building: str = typer.Option("", "--building", help="What's being built (the X)."),
    toward: str = typer.Option("", "--toward", help="The sub-problem this works toward (the Y)."),
    depends: bool = typer.Option(
        False,
        "--depends/--no-depends",
        help="Mark load-bearing: the solution depends on this assumption holding.",
    ),
    status: str = typer.Option(
        "holding", "--status", help="holding, validated, or broken."
    ),
    phase: Optional[str] = typer.Option(None, "--phase", help="Phase this belongs to (e.g. P2)."),
    college: str = typer.Option("", "--college", help="Optional richer framing for a college reader."),
    hobbyist: str = typer.Option("", "--hobbyist", help="Optional framing for a hobbyist/tinkerer."),
    reversible: bool = typer.Option(
        True, "--reversible/--irreversible", help="Whether the assumption is cheap to revisit."
    ),
    assumption_id: Optional[str] = typer.Option(
        None, "--id", help="Reuse an id to update an existing assumption (e.g. flip to broken)."
    ),
    confidence: float = typer.Option(0.0, "--confidence", min=0.0, max=1.0),
) -> None:
    """Record (or update) an assumption the agent is leaning on while building.

    This is PACERS' *Assess* — hunting the assumptions a plan depends on. The
    ``statement`` should read at a high-school level; ``--college``/``--hobbyist``
    only add framing for those readers. Re-run with the same ``--id`` to update an
    assumption's status (e.g. ``--status broken``) without duplicating it.
    """

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        notes = {}
        if college:
            notes["college"] = college
        if hobbyist:
            notes["hobbyist"] = hobbyist
        # Attribute to a phase so the review gate can require a falsifier for a
        # load-bearing assumption. Without this, a `--depends` assumption recorded
        # with no `--phase` would have phase_id=None, match no phase, and silently
        # escape the gate entirely.
        phase_id = phase if phase is not None else snapshot.current_phase
        if depends and phase_id is None:
            raise GoalsError(
                "A load-bearing (--depends) assumption must belong to a phase so the gate "
                "can require a falsifier for it. Pass --phase, or record it while a phase is "
                "active. (Use --no-depends for an assumption that isn't load-bearing.)"
            )
        fields = dict(
            statement=statement,
            building=building,
            toward=toward,
            depends_on=depends,
            status=_validate_choice(status, {"holding", "validated", "broken"}, "status"),  # type: ignore[arg-type]
            confidence=confidence,
            reversible=reversible,
            phase_id=phase_id,
            audience_notes=notes,
        )
        if assumption_id is not None:
            fields["assumption_id"] = assumption_id
        assumption = Assumption(**fields)
        append_event(
            Path.cwd(),
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.ASSUMPTION_RECORDED,
                payload={"assumption": assumption.model_dump()},
            ),
        )
        typer.echo(f"Recorded assumption: {assumption.assumption_id} ({assumption.status})")

    _handle(run)


@assess_app.command("breakdown")
def assess_breakdown(
    breakdown_json: Optional[str] = typer.Argument(None),
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Read the breakdown JSON from a file."
    ),
    problem: Optional[str] = typer.Option(
        None, "--problem", help="Rephrased problem (switches to no-JSON flag mode)."
    ),
    subproblem: Optional[list[str]] = typer.Option(
        None,
        "--subproblem",
        help='Sub-problem, repeatable. Optional tasks/questions: '
        '"statement | task1; task2 | question1; question2".',
    ),
    why: Optional[list[str]] = typer.Option(
        None, "--why", help="A step in the 5-Whys chain. Repeat for the chain."
    ),
    pause: str = typer.Option("", "--pause", help="The Pause/satisficing check."),
    system: str = typer.Option("", "--system", help="System view (for recurring problems)."),
    phase: Optional[str] = typer.Option(None, "--phase", help="Phase this belongs to (e.g. P2)."),
) -> None:
    """Record how the agent broke a goal or phase into sub-problems.

    Two ways to author it:

    - Flag mode (no JSON): ``--problem "..." --subproblem "..." [--why ...]``.
      A sub-problem may carry tasks and open questions with a simple
      ``"statement | task1; task2 | q1; q2"`` form.
    - JSON mode: a full ProblemBreakdown object inline or via ``--file`` (for the
      richer fields like per-audience notes).

    This is the artifact behind the journey's "how the agent broke the problem down".
    """

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        if problem is not None:
            if file is not None or breakdown_json is not None:
                raise GoalsError("Use flag mode (--problem) or JSON (--file/inline), not both.")
            breakdown = ProblemBreakdown(
                problem=problem,
                phase_id=phase if phase is not None else snapshot.current_phase,
                whys=why or [],
                pause_note=pause,
                system_view=system,
                subproblems=[_parse_subproblem(spec) for spec in (subproblem or [])],
            )
        else:
            if file is not None and breakdown_json is not None:
                raise GoalsError("Provide the breakdown as inline JSON or --file, not both.")
            if file is None and breakdown_json is None:
                raise GoalsError(
                    "Provide the breakdown in flag mode (--problem …) or as JSON (--file/inline)."
                )
            breakdown = _load_json_model(breakdown_json, file, ProblemBreakdown)
        append_event(
            Path.cwd(),
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.BREAKDOWN_RECORDED,
                payload={"breakdown": breakdown.model_dump()},
            ),
        )
        typer.echo(f"Recorded breakdown: {breakdown.breakdown_id}")

    _handle(run)


@assess_app.command("journey")
def assess_journey(
    audience: str = typer.Option(
        "high_school", "--audience", help="high_school, college, or hobbyist."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show the building journey in plain language at the chosen audience level."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        level = _validate_choice(
            audience, {"high_school", "college", "hobbyist"}, "audience"
        )
        if json_output:
            payload = {
                "assumptions": [a.model_dump() for a in snapshot.assumptions],
                "breakdowns": [b.model_dump() for b in snapshot.breakdowns],
                "judgements": [j.model_dump() for j in snapshot.judgements],
            }
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo(render_journey_text(snapshot, level))  # type: ignore[arg-type]

    _handle(run)


def _optional_snapshot(cwd: Path):
    try:
        return load_active_snapshot(cwd)
    except GoalsError:
        return None


def _phase_or_error(snapshot, phase_id: str) -> Phase:
    for phase in snapshot.phases:
        if phase.phase_id == phase_id:
            return phase
    valid = ", ".join(p.phase_id for p in snapshot.phases) or "none"
    raise GoalsError(f"Unknown phase id: {phase_id}. Valid phases: {valid}.")


def _checkpoint_or_none(phase: Phase, checkpoint_id: str) -> PhaseCheckpoint | None:
    for checkpoint in phase.checkpoints:
        if checkpoint.checkpoint_id == checkpoint_id:
            return checkpoint
    return None


def _validate_choice(value: str, choices: set[str], label: str) -> str:
    if value not in choices:
        raise GoalsError(f"{label} must be one of: {', '.join(sorted(choices))}")
    return value


def _user_area(value: str) -> str:
    return _validate_choice(
        value,
        {"risk", "communication", "workflow", "technical", "decision", "other"},
        "area",
    )


def _resolve_user_goal_id(goal: str) -> str:
    if goal != "current":
        return goal
    snapshot = _optional_snapshot(Path.cwd())
    return snapshot.goal_id if snapshot is not None else ""


def _personalization_or_none():
    try:
        return build_personalization_context()
    except GoalsError as exc:
        typer.echo(f"User memory warning: {exc}", err=True)
        return None


@phase_app.command("start")
def phase_start(phase_id: str) -> None:
    """Record that a phase has started."""

    def run():
        start_phase(Path.cwd(), phase_id)
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
    """Record phase evidence from a JSON object.

    Verifications only *declare* what will be checked. `ran`/`passed`/`exit_code`
    are engine-owned — they are set by `goals phase verify` (which runs the
    commands), so any values you put there are ignored.
    """

    def run():
        if file is not None and evidence_json is not None:
            raise GoalsError("Provide evidence as inline JSON or --file, not both.")
        if file is None and evidence_json is None:
            raise GoalsError("Provide evidence as inline JSON or --file.")
        evidence = _load_json_model(evidence_json, file, Evidence)
        # storage.py strips all of these engine-owned result fields on record.
        preset = sum(
            1
            for v in evidence.verifications
            if v.ran
            or v.passed
            or v.exit_code is not None
            or v.output_excerpt
            or v.ran_at
            or v.output_sha256
        )
        if preset:
            typer.echo(
                f"Note: ignored agent-set verification result fields "
                f"(ran/passed/exit_code/output_*) on {preset} verification(s) — "
                "run `goals phase verify` to record real results.",
                err=True,
            )
        record_phase_evidence(Path.cwd(), phase_id, evidence)
        typer.echo(f"Recorded evidence for {phase_id}")

    _handle(run)


@phase_app.command("verify")
def phase_verify(phase_id: str) -> None:
    """Run the phase's automated verifications and record real results.

    The engine runs each `auto` verification's command in the worktree and writes
    pass/fail from the actual exit code — the only path to a passing check. Run this
    after recording evidence and before `goals phase review`.
    """

    def run():
        report = verify_phase_workflow(Path.cwd(), phase_id)
        for r in report.results:
            mark = "PASS" if r["passed"] else "FAIL"
            typer.echo(f"  [{mark}] {r['verification_id']}")
        typer.echo(
            f"Verified {phase_id}: {report.passed_count}/{len(report.results)} automated check(s) passed."
        )
        if not report.passed:
            raise typer.Exit(1)

    _handle(run)


@phase_app.command("review")
def phase_review(phase_id: str) -> None:
    """Run the typed phase review gate."""

    def run():
        result = review_phase_workflow(Path.cwd(), phase_id)
        typer.echo(f"{result.verdict}: {result.summary}")
        if result.verdict != GateVerdict.PASS:
            if result.findings:
                for finding in result.findings:
                    typer.echo(f"  [{category_for(finding.fact_type)}] {finding.message}")
            else:
                for issue in result.p0:
                    typer.echo(f"  - {issue}")
            raise typer.Exit(1)

    _handle(run)


@phase_app.command("accept")
def phase_accept(phase_id: str) -> None:
    """Accept a reviewed phase."""

    def run():
        report = accept_phase(Path.cwd(), phase_id)
        typer.echo(f"Accepted phase {phase_id}")
        if report.warning:
            typer.echo(report.warning, err=True)
        if report.completion_note:
            typer.echo(report.completion_note)
        if report.memory_digest:
            typer.echo(report.memory_digest)
        if report.interview:
            typer.echo(report.interview)

    _handle(run)


@skills_app.command("list")
def skills_list(
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """List skills discovered in agent skill dirs and bundled Goals skills."""

    def run():
        skills = list_skills_workflow()
        if json_output:
            typer.echo(json.dumps([skill.model_dump() for skill in skills], indent=2))
        else:
            typer.echo(render_skills_list(skills))

    _handle(run)


@skills_app.command("install")
def skills_install(
    target: str = typer.Option(
        ...,
        "--target",
        help="Where to install goals' bundled skills: claude, codex, or both.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite an existing differing same-named skill (replaces your version).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Optionally install goals' bundled skills into an agent's skill dir."""

    def run():
        choice = _validate_choice(target, {"claude", "codex", "both"}, "target")
        targets = ["claude", "codex"] if choice == "both" else [choice]
        report = install_skills_workflow(targets, force=force)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_install_report(report))

    _handle(run)


@skills_app.command("preflight")
def skills_preflight(
    objective: Optional[str] = typer.Argument(
        None, help="Objective to classify. Defaults to the active goal objective."
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero when required capabilities are missing."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Infer needed capabilities and surface missing or unavailable skills."""

    def run():
        target = objective
        if target is None:
            target = load_active_snapshot(Path.cwd()).objective
        report = preflight_skills(target)
        if json_output:
            typer.echo(report.model_dump_json(indent=2))
        else:
            typer.echo(render_skill_capability_report(report))
        if strict and not report.passed:
            raise typer.Exit(1)

    _handle(run)


@skills_app.command("import")
def skills_import(
    source: Path = typer.Argument(..., help="Directory containing a SKILL.md to quarantine."),
    name: str = typer.Option("", "--name", help="Quarantine name; defaults to the source dir name."),
) -> None:
    """Copy an external skill into quarantine for review, not execution."""

    def run():
        target = import_skill(source, name)
        typer.echo(f"Quarantined skill for review: {target}")
        typer.echo("Review provenance and contents before promoting it into an agent skill dir.")

    _handle(run)


def _default_loop_out(out: Optional[Path]) -> Path:
    return out.expanduser() if out is not None else Path.cwd() / ".goals"


def _parse_loop_answers(items: list[str] | None) -> dict[str, str]:
    answers: dict[str, str] = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise GoalsError("--answer must be KEY=value, for example --answer N=5.")
        answers[key.strip()] = value.strip()
    return answers


def _loop_artifacts(out_dir: Path) -> list[Path]:
    names = ("loop-design.json", "goal-state.json", "GOAL.md", "loop.html")
    return [out_dir / name for name in names if (out_dir / name).exists()]


@loop_app.command("build")
def loop_build(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Directory to save the loop into (default: ./.goals)."
    ),
    script: Optional[Path] = typer.Option(
        None, "--script", help="Run builder commands from a file instead of prompting."
    ),
    append: bool = typer.Option(
        False,
        "--append",
        help="When replaying --script, append to an existing design instead of rebuilding from empty.",
    ),
) -> None:
    """Interactively compose a goal loop (or replay a command script)."""

    def run():
        out_dir = _default_loop_out(out)
        session = new_session(out_dir)
        design_file = out_dir / "loop-design.json"
        if design_file.exists() and (script is None or append):
            session.design = load_design(design_file)
            typer.echo(f"Loaded existing design from {design_file}")
        elif design_file.exists() and script is not None:
            typer.echo(f"Rebuilding from empty design; use --append to extend {design_file}")
        if script is not None:
            if not script.exists():
                raise GoalsError(f"Script not found: {script}")
            commands = script.read_text(encoding="utf-8").splitlines()
            run_script(session, commands, write=typer.echo)
        else:
            run_builder(session, write=typer.echo)

    _handle(run)


@loop_app.command("import")
def loop_import(
    source: str = typer.Argument(
        ...,
        help="Loop source: URL, local file, directory, builder script, catalog JSON/YAML, or '-'.",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Directory to save the loop into (default: ./.goals)."
    ),
    select: str = typer.Option(
        "",
        "--select",
        help="Loop id/slug/title when the source contains more than one loop.",
    ),
    answer: Optional[list[str]] = typer.Option(
        None,
        "--answer",
        help="Answer an import placeholder as KEY=value. Repeat for multiple answers.",
    ),
    no_prompt: bool = typer.Option(
        False,
        "--no-prompt",
        help="Do not ask questions; fail if --select or --answer is required.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing loop artifacts in --out.",
    ),
) -> None:
    """Import an external loop definition into Goals loop-design artifacts."""

    def run():
        out_dir = _default_loop_out(out)
        profile_root = profile_root_for_loop_path(out_dir, cwd=Path.cwd())
        existing = _loop_artifacts(out_dir)
        if existing and not force:
            found = ", ".join(str(path) for path in existing)
            raise GoalsError(
                "Refusing to overwrite existing loop artifacts. "
                f"Use --force to replace: {found}"
            )
        interactive = sys.stdin.isatty() and not no_prompt

        def ask_selection(candidates):
            typer.echo("Source contains multiple loops:")
            for index, candidate in enumerate(candidates, start=1):
                typer.echo(f"{index}. {candidate.candidate_id} — {candidate.title}")
            choice = typer.prompt("Import which loop? Enter number, slug, or title")
            if choice.isdigit():
                index = int(choice)
                if 1 <= index <= len(candidates):
                    return candidates[index - 1].candidate_id
            return choice

        def ask_question(question):
            if question.default:
                return typer.prompt(question.prompt, default=question.default)
            return typer.prompt(question.prompt)

        result = import_loop_design(
            source,
            select=select,
            answers=_parse_loop_answers(answer),
            ask_selection=ask_selection if interactive else None,
            ask_question=ask_question if interactive else None,
            root=Path.cwd(),
        )
        saved = save_design(result.design, out_dir, profile_root=profile_root)
        typer.echo(render_import_result(result, design_path=saved.design_path))

    _handle(run)


@loop_app.command("activate")
def loop_activate(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Directory holding loop-design.json (default: ./.goals)."
    ),
    agent: ModeAAdapter = typer.Option(
        "auto",
        "--agent",
        "--adapter",
        help="Native agent to prepare instructions for.",
    ),
    autonomy: str = typer.Option("standard", help="careful, standard, fast, or swarm"),
    worktree: bool = typer.Option(False, "--worktree", help="Force an isolated worktree."),
    in_place: bool = typer.Option(False, "--in-place", help="Work on the current branch."),
) -> None:
    """Start an executable goal from a saved loop design."""

    def run():
        if worktree and in_place:
            raise GoalsError("Choose either --worktree or --in-place, not both.")
        requested = "worktree" if worktree else "in_place" if in_place else "auto"
        loop_dir = _default_loop_out(out)
        profile_root = profile_root_for_loop_path(loop_dir, cwd=Path.cwd())
        report = start_workflow(
            "",
            Path.cwd(),
            agent=agent,
            autonomy=autonomy,
            workspace=requested,
            loop=loop_dir,
            profile_root=profile_root,
        )
        typer.echo(render_start_workflow(report))

    _handle(run)


@loop_app.command("export")
def loop_export(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Directory holding loop-design.json (default: ./.goals)."
    ),
    html_only: bool = typer.Option(
        False, "--html-only", help="Only re-render the HTML, not the portable spec."
    ),
) -> None:
    """Re-render a saved loop design to HTML (and the portable spec)."""

    def run():
        out_dir = _default_loop_out(out)
        profile_root = profile_root_for_loop_path(out_dir, cwd=Path.cwd())
        design = load_design(out_dir)
        if html_only:
            html_path = out_dir / "loop.html"
            atomic_write_text(html_path, render_loop_html(design, profile_root=profile_root))
            typer.echo(f"Wrote {html_path}")
        else:
            result = save_design(design, out_dir, profile_root=profile_root)
            typer.echo(f"Wrote {result.html_path}, {result.state_path}, {result.markdown_path}")

    _handle(run)


@loop_app.command("check")
def loop_check(
    out: Optional[Path] = typer.Option(
        None, "--out", help="Directory holding loop-design.json (default: ./.goals)."
    ),
    fix: bool = typer.Option(
        False, "--fix", help="Apply safe, reversible fixes and re-save the design."
    ),
    target_agent: Optional[str] = typer.Option(
        None,
        "--target-agent",
        help="Require referenced skills to be installed for claude or codex.",
    ),
) -> None:
    """Lint a designed loop for issues (and optionally auto-fix the safe ones)."""

    def run():
        out_dir = _default_loop_out(out)
        profile_root = profile_root_for_loop_path(out_dir, cwd=Path.cwd())
        design = load_design(out_dir)
        target = (
            cast(AgentName, _validate_choice(target_agent, {"claude", "codex"}, "target-agent"))
            if target_agent is not None
            else None
        )
        if fix:
            fixed, changes = apply_fixes(design, target_agent=target, profile_root=profile_root)
            if changes:
                save_design(fixed, out_dir, profile_root=profile_root)
            typer.echo(render_fix_summary(changes))
            design = fixed
        report = check_loop(design, target_agent=target, profile_root=profile_root)
        typer.echo(render_loop_check_report(report))
        if report.has_blocking:
            raise typer.Exit(1)

    _handle(run)


@loop_app.command("detect")
def loop_detect(phase_id: str) -> None:
    """Detect and log regressions for a phase (run after it is accepted)."""

    def run():
        snapshot = load_active_snapshot(Path.cwd())
        report = log_phase_regression(Path.cwd(), snapshot, phase_id)
        typer.echo(render_regression_report(report))

    _handle(run)


@loop_app.command("improve")
def loop_improve(
    apply: bool = typer.Option(
        False, "--apply", help="Apply the safe, reversible loop-design fixes (approval)."
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Directory holding loop-design.json (default: ./.goals)."
    ),
) -> None:
    """Turn accumulated, evidence-backed memory into a reviewable change set."""

    def run():
        # Snapshot is optional: the design-first flow (a saved loop, no active
        # goal yet) can still surface and apply the safe loop-design fixes.
        snapshot = _optional_snapshot(Path.cwd())
        design_dir = _default_loop_out(out)
        if not (design_dir / "loop-design.json").exists():
            design_dir = None
        if snapshot is None and design_dir is None:
            raise GoalsError(
                "Nothing to improve: no active goal and no loop-design.json found. "
                "Run `goals loop build` or `goals start` first."
            )
        if apply:
            plan = apply_loop_improvements(Path.cwd(), snapshot, design_dir=design_dir)
        else:
            plan = plan_loop_improvements(Path.cwd(), snapshot, design_dir=design_dir)
        typer.echo(render_loop_improvement_plan(plan))

    _handle(run)


@hooks_app.command("session-start")
def hooks_session_start() -> None:
    """Emit the SessionStart payload (active goal context) for the plugin hook."""
    typer.echo(session_start_payload(Path.cwd()), nl=False)


@hooks_app.command("stop")
def hooks_stop() -> None:
    """Emit the Stop payload (opt-in phase gate via GOALS_ENFORCE)."""
    typer.echo(stop_payload(Path.cwd()), nl=False)


@app.command(rich_help_panel="Portability")
def setup(
    agent: str = typer.Option(..., "--agent", help="Wire up: claude, codex, or both."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying."),
) -> None:
    """One command to make goals work inside Claude Code and/or Codex."""

    def run():
        choice = _validate_choice(agent, {"claude", "codex", "both"}, "agent")
        targets = ["claude", "codex"] if choice == "both" else [choice]
        report = setup_agents(targets, dry_run=dry_run)
        typer.echo(render_setup_report(report))

    _handle(run)


@app.command(rich_help_panel="Simple workflow")
def diagram(
    source: str = typer.Option(
        "architecture", "--source", help="What to diagram: architecture or loop."
    ),
    fmt: str = typer.Option("mermaid", "--format", help="Output format: mermaid or excalidraw."),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Write to a file instead of stdout."
    ),
) -> None:
    """Generate a clean diagram of the goal architecture or designed loop."""

    def run():
        src = _validate_choice(source, {"architecture", "loop"}, "source")
        fmt_choice = _validate_choice(fmt, {"mermaid", "excalidraw"}, "format")
        if src == "architecture":
            snapshot = load_active_snapshot(Path.cwd())
            content = render_architecture_diagram(
                architecture_for_snapshot(snapshot), fmt=fmt_choice
            )
        else:
            design = load_design(Path.cwd() / ".goals")
            content = render_loop_diagram(design, fmt=fmt_choice)
        if out is not None:
            atomic_write_text(out, content)
            typer.echo(f"Wrote {out}")
        else:
            typer.echo(content)

    _handle(run)


if __name__ == "__main__":
    app()
