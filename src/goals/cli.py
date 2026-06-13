from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from goals.adapters import adapter_check
from goals.evaluations import evaluate_goal_scenarios
from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.models import Event, EventType, Evidence, GateVerdict
from goals.registry import validate_registries
from goals.runtime import (
    append_event,
    claim_worktree,
    create_goal,
    emit_dashboard,
    load_active_snapshot,
    run_gate,
    transition_phase,
)
from goals.scanners import run_safety_scanners
from goals.storage import EventStore, GoalsError, atomic_write_text

app = typer.Typer(help="Goals helps AI agents finish bigger tasks without losing track.")
adapter_app = typer.Typer(help="Native goal loop adapters.")
eval_app = typer.Typer(help="Evaluate Goals use-case coverage.")
phase_app = typer.Typer(help="Agent phase protocol.")
app.add_typer(adapter_app, name="adapter")
app.add_typer(eval_app, name="eval")
app.add_typer(phase_app, name="phase")


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
