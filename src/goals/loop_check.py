"""Loop evaluation — a linter for designed goal loops.

``goals loop check`` analyzes a :class:`~goals.loop_builder.LoopDesign` and
reports P0/P1/P2 issues with concrete fixes. ``--fix`` applies only the safe,
reversible suggestions and reports what it changed.

The detectors are deliberately deterministic (no model calls) so a failing-loop
fixture is flagged the same way every run and a healthy loop passes clean.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from goals.loop_builder import LoopDesign, LoopPhase
from goals.skill_discovery import DiscoveredSkill, discover_skills

Severity = Literal["p0", "p1", "p2"]

#: A default termination condition `--fix` adds when a loop has none.
DEFAULT_TERMINATION = "All acceptance criteria for the final phase are met."
#: A default evidence requirement `--fix` adds to a phase that lacks one.
DEFAULT_EVIDENCE_CRITERION = "Evidence is recorded (tests or checks run)."

# Phrases that make an acceptance criterion untestable, and concrete signals
# that make it verifiable. A criterion is vague if it uses a vague phrase, or if
# it carries no concrete signal at all.
_VAGUE_PHRASES = (
    "works correctly",
    "works well",
    "good enough",
    "looks good",
    "make it work",
    "as needed",
    "properly",
    "somehow",
    " etc",
    "etc.",
)
_CONCRETE_SIGNALS = (
    "test",
    "pass",
    "fail",
    "render",
    "return",
    "visible",
    "exist",
    "record",
    "file",
    "command",
    "output",
    "error",
    "check",
    "verif",
    "measur",
    "count",
    "match",
    "equal",
    "empty",
    "zero",
    "no ",
)
_EVIDENCE_SIGNALS = (
    "test",
    "check",
    "evidence",
    "proof",
    "verif",
    "measur",
    "record",
)


class LoopCheckFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    code: str
    summary: str
    suggested_fix: str
    phase_id: str | None = None
    auto_fixable: bool = False


class LoopCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    summary: str
    findings: list[LoopCheckFinding] = Field(default_factory=list)

    @property
    def has_blocking(self) -> bool:
        return any(finding.severity == "p0" for finding in self.findings)


def check_loop(
    design: LoopDesign, *, skills: list[DiscoveredSkill] | None = None
) -> LoopCheckReport:
    """Run every detector and return a severity-sorted report."""
    discovered = skills if skills is not None else discover_skills()
    known = {skill.name for skill in discovered}
    findings: list[LoopCheckFinding] = []
    findings += _check_no_progress(design)
    findings += _check_termination(design)
    findings += _check_duplicate_and_empty_phases(design)
    findings += _check_vague_acceptance(design)
    findings += _check_skill_refs(design, known)
    findings += _check_evidence_requirement(design)
    findings.sort(key=lambda f: _SEVERITY_ORDER[f.severity])
    passed = not findings
    if passed:
        summary = "Loop looks healthy: no issues found."
    else:
        counts = {sev: sum(1 for f in findings if f.severity == sev) for sev in ("p0", "p1", "p2")}
        summary = (
            f"{len(findings)} issue(s): "
            f"{counts['p0']} P0, {counts['p1']} P1, {counts['p2']} P2."
        )
    return LoopCheckReport(passed=passed, summary=summary, findings=findings)


_SEVERITY_ORDER = {"p0": 0, "p1": 1, "p2": 2}


# --------------------------------------------------------------------------- #
# Detectors
# --------------------------------------------------------------------------- #
def _check_no_progress(design: LoopDesign) -> list[LoopCheckFinding]:
    if not design.phases:
        return [
            LoopCheckFinding(
                severity="p0",
                code="no-phases",
                summary="The loop has no phases, so it can never make progress.",
                suggested_fix="Add at least one phase with `add <title>`.",
            )
        ]
    if not any(phase.acceptance_criteria for phase in design.phases):
        return [
            LoopCheckFinding(
                severity="p1",
                code="no-acceptance",
                summary="No phase has any acceptance criteria, so progress cannot be verified.",
                suggested_fix="Add an observable acceptance criterion to at least one phase.",
            )
        ]
    return []


def _check_termination(design: LoopDesign) -> list[LoopCheckFinding]:
    if not design.phases:
        return []  # already reported by no-progress
    if any(phase.termination_conditions for phase in design.phases):
        return []
    return [
        LoopCheckFinding(
            severity="p0",
            code="no-termination",
            summary="The loop has no termination condition, so it may run forever.",
            suggested_fix=f"Add a termination condition (e.g. {DEFAULT_TERMINATION!r}).",
            auto_fixable=True,
        )
    ]


def _check_duplicate_and_empty_phases(design: LoopDesign) -> list[LoopCheckFinding]:
    findings: list[LoopCheckFinding] = []
    ids = [phase.phase_id for phase in design.phases]
    for dup in sorted({pid for pid in ids if ids.count(pid) > 1}):
        findings.append(
            LoopCheckFinding(
                severity="p1",
                code="duplicate-phase-id",
                summary=f"Phase id {dup!r} is used by more than one phase.",
                suggested_fix="Give each phase a unique id (auto-fix reassigns one).",
                phase_id=dup,
                auto_fixable=True,
            )
        )
    seen: dict[tuple[str, str], str] = {}
    for phase in design.phases:
        key = (phase.title.strip().lower(), phase.goal.strip().lower())
        if key in seen and phase.title.strip():
            findings.append(
                LoopCheckFinding(
                    severity="p2",
                    code="duplicate-phase",
                    summary=f"Phase {phase.phase_id} duplicates {seen[key]} (same title and goal).",
                    suggested_fix="Merge or differentiate the duplicate phases.",
                    phase_id=phase.phase_id,
                )
            )
        else:
            seen[key] = phase.phase_id
        if _is_empty_phase(phase):
            findings.append(
                LoopCheckFinding(
                    severity="p2",
                    code="empty-phase",
                    summary=f"Phase {phase.phase_id} has no goal, acceptance, termination, or skill.",
                    suggested_fix="Give the phase work to do, or delete it.",
                    phase_id=phase.phase_id,
                )
            )
    return findings


def _check_vague_acceptance(design: LoopDesign) -> list[LoopCheckFinding]:
    findings: list[LoopCheckFinding] = []
    for phase in design.phases:
        for criterion in phase.acceptance_criteria:
            if _is_vague(criterion):
                findings.append(
                    LoopCheckFinding(
                        severity="p1",
                        code="vague-acceptance",
                        summary=f"Phase {phase.phase_id} has an untestable criterion: {criterion!r}.",
                        suggested_fix=(
                            "Rewrite as an observable check (a passing test, a visible "
                            "output, or a measurable threshold)."
                        ),
                        phase_id=phase.phase_id,
                    )
                )
    return findings


def _check_skill_refs(design: LoopDesign, known: set[str]) -> list[LoopCheckFinding]:
    findings: list[LoopCheckFinding] = []
    for phase in design.phases:
        for name in phase.skills:
            if name not in known:
                findings.append(
                    LoopCheckFinding(
                        severity="p1",
                        code="unknown-skill",
                        summary=(
                            f"Phase {phase.phase_id} references skill {name!r}, which is not in "
                            "~/.claude/skills or ~/.codex/skills."
                        ),
                        suggested_fix="Install the skill, rename the reference, or remove it.",
                        phase_id=phase.phase_id,
                    )
                )
    return findings


def _check_evidence_requirement(design: LoopDesign) -> list[LoopCheckFinding]:
    findings: list[LoopCheckFinding] = []
    for phase in design.phases:
        if not phase.acceptance_criteria:
            continue  # no-acceptance already covers the empty case
        if not any(_mentions_evidence(c) for c in phase.acceptance_criteria):
            findings.append(
                LoopCheckFinding(
                    severity="p2",
                    code="no-evidence-requirement",
                    summary=f"Phase {phase.phase_id} never requires evidence (a test, check, or proof).",
                    suggested_fix=f"Add an evidence criterion (e.g. {DEFAULT_EVIDENCE_CRITERION!r}).",
                    phase_id=phase.phase_id,
                    auto_fixable=True,
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Auto-fix (safe, reversible suggestions only)
# --------------------------------------------------------------------------- #
def apply_fixes(
    design: LoopDesign, *, skills: list[DiscoveredSkill] | None = None
) -> tuple[LoopDesign, list[str]]:
    """Return a fixed copy of the design plus a list of changes applied.

    Only auto-fixable findings are applied. Idempotent: a design that already
    passes (or whose only issues are non-auto-fixable) is returned unchanged with
    an empty change list.
    """
    fixed = design.model_copy(deep=True)
    changes: list[str] = []
    report = check_loop(fixed, skills=skills)
    codes = {finding.code for finding in report.findings if finding.auto_fixable}

    if "duplicate-phase-id" in codes:
        changes += _fix_duplicate_ids(fixed)
    if "no-termination" in codes and fixed.phases:
        fixed.phases[-1].termination_conditions.append(DEFAULT_TERMINATION)
        changes.append(
            f"Added termination condition to {fixed.phases[-1].phase_id}: {DEFAULT_TERMINATION}"
        )
    if "no-evidence-requirement" in codes:
        # Re-check after structural fixes so phase ids in the report are current.
        for finding in check_loop(fixed, skills=skills).findings:
            if finding.code == "no-evidence-requirement" and finding.phase_id:
                phase = _phase(fixed, finding.phase_id)
                if phase is not None:
                    phase.acceptance_criteria.append(DEFAULT_EVIDENCE_CRITERION)
                    changes.append(
                        f"Added evidence criterion to {phase.phase_id}: "
                        f"{DEFAULT_EVIDENCE_CRITERION}"
                    )
    return fixed, changes


def _fix_duplicate_ids(design: LoopDesign) -> list[str]:
    from goals.loop_builder import _next_phase_id

    changes: list[str] = []
    seen: set[str] = set()
    for phase in design.phases:
        if phase.phase_id in seen:
            old = phase.phase_id
            # Temporarily blank so _next_phase_id does not count this slot.
            phase.phase_id = ""
            phase.phase_id = _next_phase_id(design)
            seen.add(phase.phase_id)
            changes.append(f"Reassigned duplicate phase id {old} -> {phase.phase_id}")
        else:
            seen.add(phase.phase_id)
    return changes


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_loop_check_report(report: LoopCheckReport) -> str:
    lines = [report.summary]
    for finding in report.findings:
        where = f" [{finding.phase_id}]" if finding.phase_id else ""
        flag = " (auto-fixable)" if finding.auto_fixable else ""
        lines.append(f"- {finding.severity.upper()} {finding.code}{where}{flag}: {finding.summary}")
        lines.append(f"    Fix: {finding.suggested_fix}")
    return "\n".join(lines)


def render_fix_summary(changes: list[str]) -> str:
    if not changes:
        return "No safe auto-fixes to apply."
    return "Applied fixes:\n" + "\n".join(f"- {change}" for change in changes)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _is_empty_phase(phase: LoopPhase) -> bool:
    return not (
        phase.goal.strip()
        or phase.acceptance_criteria
        or phase.termination_conditions
        or phase.skills
    )


def _is_vague(criterion: str) -> bool:
    lowered = criterion.lower()
    if any(phrase in lowered for phrase in _VAGUE_PHRASES):
        return True
    if any(char.isdigit() for char in lowered):
        return False
    return not any(signal in lowered for signal in _CONCRETE_SIGNALS)


def _mentions_evidence(criterion: str) -> bool:
    lowered = criterion.lower()
    return any(signal in lowered for signal in _EVIDENCE_SIGNALS)


def _phase(design: LoopDesign, phase_id: str) -> LoopPhase | None:
    return next((phase for phase in design.phases if phase.phase_id == phase_id), None)
