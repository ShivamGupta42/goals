"""Per-phase regression detection and the opt-in self-improvement loop.

After a phase runs, :func:`detect_phase_regression` inspects its evidence and
review for signs something went wrong. :func:`log_phase_regression` records each
finding — *with evidence* — into the existing self-evolution memory and routes
it:

* **improve-now** (blocking): surfaced to the user immediately.
* **defer**: recorded silently; never acted on without explicit approval.

``goals loop improve`` then turns the accumulated, evidence-backed memory into a
concrete, reviewable change set — targeting either task execution or the loop
design itself — and applies only the safe, reversible loop-design fixes on
approval. It reuses :mod:`goals.memory` (record + derive suggestions) and
:mod:`goals.loop_check` (safe auto-fixes); it does not reinvent either.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from goals.loop_builder import load_design, save_design
from goals.loop_check import apply_fixes, check_loop
from goals.memory import derive_memory_suggestions, load_memory, save_memory
from goals.models import GateVerdict, GoalSnapshot, Phase, SelfEvolutionEntry
from goals.storage import GoalsError

Severity = Literal["p0", "p1", "p2"]
Routing = Literal["improve_now", "defer"]

#: Confidence below which a phase that claims acceptance is treated as risky.
LOW_CONFIDENCE = 0.5

_MEM_SEVERITY = {"p0": "high", "p1": "medium", "p2": "low"}
# Memory areas whose lessons point at the loop's shape rather than execution.
_LOOP_DESIGN_AREAS = {"phase", "gate"}
# Review verdicts that must surface to the user, not defer — a blocked or
# needs-human review is the same severity class as an itemized P0.
_BLOCKING_VERDICTS = {GateVerdict.BLOCKED, GateVerdict.UNSAFE, GateVerdict.NEEDS_HUMAN}


class RegressionFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    area: Literal["phase", "gate", "safety", "decision", "other"]
    summary: str
    routing: Routing
    evidence_refs: list[str] = Field(default_factory=list)


class RegressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    phase_id: str
    surfaced: list[RegressionFinding] = Field(default_factory=list)
    deferred: list[RegressionFinding] = Field(default_factory=list)
    recorded: int = 0
    summary: str


class LoopImprovement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: Literal["execution", "loop-design"]
    title: str
    detail: str
    source: Literal["memory", "loop-check"]
    auto_applicable: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class LoopImprovementPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    dry_run: bool = True
    summary: str
    improvements: list[LoopImprovement] = Field(default_factory=list)
    applied: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def detect_phase_regression(snapshot: GoalSnapshot, phase_id: str) -> list[RegressionFinding]:
    """Inspect one phase for regressions. improve-now ⇔ a P0 (blocking) finding."""
    phase = _phase(snapshot, phase_id)
    findings: list[RegressionFinding] = []
    refs = [f"phase:{phase_id}", snapshot.goal_id]

    evidence = phase.evidence
    if evidence is not None:
        if evidence.acceptance_not_met:
            findings.append(
                RegressionFinding(
                    severity="p0",
                    area="gate",
                    summary=(
                        f"Phase {phase_id} reports unmet acceptance: "
                        f"{'; '.join(evidence.acceptance_not_met)}"
                    ),
                    routing="improve_now",
                    evidence_refs=[*refs, f"evidence:{phase_id}"],
                )
            )
        if evidence.acceptance_met and evidence.confidence < LOW_CONFIDENCE:
            findings.append(
                RegressionFinding(
                    severity="p1",
                    area="gate",
                    summary=(
                        f"Phase {phase_id} claims acceptance at low confidence "
                        f"({evidence.confidence:.2f})."
                    ),
                    routing="defer",
                    evidence_refs=[*refs, f"evidence:{phase_id}"],
                )
            )
        for gap in evidence.known_gaps:
            findings.append(
                RegressionFinding(
                    severity="p2",
                    area="phase",
                    summary=f"Phase {phase_id} has a known gap: {gap}",
                    routing="defer",
                    evidence_refs=[*refs, f"evidence:{phase_id}"],
                )
            )
        for ambiguous in evidence.ambiguous:
            findings.append(
                RegressionFinding(
                    severity="p2",
                    area="decision",
                    summary=f"Phase {phase_id} left an ambiguity: {ambiguous}",
                    routing="defer",
                    evidence_refs=[*refs, f"evidence:{phase_id}"],
                )
            )

    if phase.reviews:
        last = phase.reviews[-1]
        if last.verdict != GateVerdict.PASS:
            blocking = bool(last.p0) or last.verdict in _BLOCKING_VERDICTS
            findings.append(
                RegressionFinding(
                    severity="p0" if blocking else "p1",
                    area="safety" if last.verdict == GateVerdict.UNSAFE else "gate",
                    summary=(
                        f"Phase {phase_id} latest review verdict is {last.verdict}: {last.summary}"
                    ),
                    routing="improve_now" if blocking else "defer",
                    evidence_refs=[*refs, f"review:{phase_id}"],
                )
            )
    return findings


def log_phase_regression(cwd: Path, snapshot: GoalSnapshot, phase_id: str) -> RegressionReport:
    """Record each regression finding into memory with evidence, then route it.

    Idempotent: findings are deduped by content (goal, area, note, phase) so
    re-running after the same accepted phase does not pile up duplicate entries.
    """
    findings = detect_phase_regression(snapshot, phase_id)
    memory = load_memory(cwd, snapshot)
    # Dedup by content so re-running is idempotent. Severity is part of the key
    # so two distinct findings that share a summary are not collapsed; the key
    # mirrors the entry fields (note holds the summary), so it also matches
    # entries written by a prior run.
    existing = {(e.goal_id, e.area, e.note, e.phase_id, e.severity) for e in memory.entries}
    added = 0
    for finding in findings:
        key = (
            snapshot.goal_id,
            finding.area,
            finding.summary,
            phase_id,
            _MEM_SEVERITY[finding.severity],
        )
        if key in existing:
            continue
        existing.add(key)
        memory.entries.append(
            SelfEvolutionEntry(
                kind="friction",
                area=finding.area,
                note=finding.summary,
                severity=_MEM_SEVERITY[finding.severity],  # type: ignore[arg-type]
                goal_id=snapshot.goal_id,
                phase_id=phase_id,
                evidence_refs=finding.evidence_refs,
            )
        )
        added += 1
    if added:
        save_memory(cwd, memory, snapshot)
    surfaced = [f for f in findings if f.routing == "improve_now"]
    deferred = [f for f in findings if f.routing == "defer"]
    already_known = len(findings) - added
    if not findings:
        summary = f"No regressions detected for {phase_id}."
    else:
        provenance = (
            f"{added} newly recorded, {already_known} already known"
            if added and already_known
            else f"{added} newly recorded"
            if added
            else "all already recorded"
        )
        summary = (
            f"{len(findings)} regression(s) for {phase_id} "
            f"({len(surfaced)} need attention now, {len(deferred)} deferred; {provenance})."
        )
    return RegressionReport(
        goal_id=snapshot.goal_id,
        phase_id=phase_id,
        surfaced=surfaced,
        deferred=deferred,
        recorded=added,
        summary=summary,
    )


# --------------------------------------------------------------------------- #
# Improvement loop
# --------------------------------------------------------------------------- #
def plan_loop_improvements(
    cwd: Path, snapshot: GoalSnapshot | None = None, *, design_dir: Path | None = None
) -> LoopImprovementPlan:
    """Build a reviewable change set from accumulated memory + loop-design fixes.

    Memory-derived improvements are advisory (``auto_applicable=False``). The
    only directly-applicable improvements are the safe loop-design fixes from the
    Phase-2 linter, included when a saved design is found. ``snapshot`` is
    optional so the design-first flow (a saved loop with no active goal yet) can
    still surface loop-design fixes.
    """
    improvements = _memory_improvements(cwd, snapshot)
    improvements += _loop_design_improvements(design_dir, profile_root=cwd)
    auto = sum(1 for imp in improvements if imp.auto_applicable)
    if not improvements:
        summary = "No accumulated suggestions; nothing to improve."
    else:
        summary = (
            f"{len(improvements)} proposed improvement(s); {auto} can be applied automatically. "
            "Re-run with --apply to apply the safe loop-design fixes."
        )
    return LoopImprovementPlan(
        goal_id=snapshot.goal_id if snapshot else "",
        dry_run=True,
        summary=summary,
        improvements=improvements,
    )


def apply_loop_improvements(
    cwd: Path, snapshot: GoalSnapshot | None = None, *, design_dir: Path | None = None
) -> LoopImprovementPlan:
    """Apply only the safe, reversible loop-design fixes; a no-op otherwise."""
    plan = plan_loop_improvements(cwd, snapshot, design_dir=design_dir)
    applied: list[str] = []
    if design_dir is not None and (design_dir / "loop-design.json").exists():
        design = load_design(design_dir)
        fixed, changes = apply_fixes(design, profile_root=cwd)
        if changes:
            save_design(fixed, design_dir, profile_root=cwd)
            applied = changes
    summary = (
        f"Applied {len(applied)} safe loop-design fix(es)."
        if applied
        else "No safe, approved improvements to apply."
    )
    return plan.model_copy(update={"dry_run": False, "applied": applied, "summary": summary})


def _memory_improvements(cwd: Path, snapshot: GoalSnapshot | None) -> list[LoopImprovement]:
    suggestions = derive_memory_suggestions(load_memory(cwd, snapshot))
    improvements: list[LoopImprovement] = []
    for suggestion in suggestions:
        target = "loop-design" if suggestion.area in _LOOP_DESIGN_AREAS else "execution"
        improvements.append(
            LoopImprovement(
                target=target,
                title=suggestion.title,
                detail=suggestion.recommended_change,
                source="memory",
                auto_applicable=False,
                evidence_refs=suggestion.evidence_refs,
            )
        )
    return improvements


def _loop_design_improvements(
    design_dir: Path | None,
    *,
    profile_root: Path,
) -> list[LoopImprovement]:
    if design_dir is None or not (design_dir / "loop-design.json").exists():
        return []
    design = load_design(design_dir)
    return [
        LoopImprovement(
            target="loop-design",
            title=f"Fix {finding.code}",
            detail=finding.suggested_fix,
            source="loop-check",
            auto_applicable=True,
            evidence_refs=[finding.phase_id] if finding.phase_id else [],
        )
        for finding in check_loop(design, profile_root=profile_root).findings
        if finding.auto_fixable
    ]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_regression_report(report: RegressionReport) -> str:
    lines = [report.summary]
    if report.surfaced:
        lines.append("Needs attention now:")
        lines += [f"- {f.severity.upper()} {f.summary}" for f in report.surfaced]
    if report.deferred:
        lines.append("Deferred (recorded, awaiting approval):")
        lines += [f"- {f.severity.upper()} {f.summary}" for f in report.deferred]
    return "\n".join(lines)


def render_loop_improvement_plan(plan: LoopImprovementPlan) -> str:
    lines = [plan.summary]
    for imp in plan.improvements:
        flag = " (auto)" if imp.auto_applicable else ""
        lines.append(f"- [{imp.target}]{flag} {imp.title}: {imp.detail}")
    if not plan.dry_run and plan.applied:
        lines.append("Applied:")
        lines += [f"- {change}" for change in plan.applied]
    return "\n".join(lines)


def _phase(snapshot: GoalSnapshot, phase_id: str) -> Phase:
    for phase in snapshot.phases:
        if phase.phase_id == phase_id:
            return phase
    raise GoalsError(f"Unknown phase id: {phase_id}")
