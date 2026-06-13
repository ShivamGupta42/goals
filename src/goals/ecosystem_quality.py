from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from goals.models import EcosystemQualityFinding, EcosystemQualityReport
from goals.registry import validate_registry_file
from goals.storage import GoalsError

BROAD_TERMS = {
    "all",
    "anything",
    "everything",
    "general",
    "help",
    "misc",
    "other",
    "stuff",
    "task",
    "tool",
    "work",
}
LOCAL_PATH_PATTERNS = (
    re.compile(r"/" + r"Users" + r"/[^\s`'\"]+"),
    re.compile(r"[A-Za-z]:\\\\"),
)
VALID_RISKS = {"low", "medium", "high"}


def audit_ecosystem_quality(worktree: Path) -> EcosystemQualityReport:
    registry_root = _registry_root(worktree)
    registry_paths = [
        path
        for path in (registry_root / "skills.yml", registry_root / "plugins.yml")
        if path.exists()
    ]
    findings: list[EcosystemQualityFinding] = []
    entry_count = 0
    for path in registry_paths:
        try:
            data = validate_registry_file(path)
        except GoalsError as exc:
            findings.append(
                EcosystemQualityFinding(
                    severity="p0",
                    kind="registry",
                    name=path.name,
                    area="schema",
                    summary=f"{path.name} fails registry schema validation.",
                    recommendation="Fix the schema before using this registry for automatic routing.",
                    evidence=[str(exc)],
                )
            )
            continue
        kind = str(data.get("kind", ""))
        entries = data.get(kind, {})
        if not isinstance(entries, dict):
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            entry_count += 1
            findings.extend(_entry_findings(kind[:-1], str(name), entry))

    blocking = [finding for finding in findings if finding.severity in {"p0", "p1"}]
    return EcosystemQualityReport(
        passed=not blocking,
        summary=(
            f"Audited {entry_count} ecosystem registry entr{'y' if entry_count == 1 else 'ies'} "
            f"across {len(registry_paths)} registry file(s): "
            f"{len([f for f in findings if f.severity == 'p0'])} blocking, "
            f"{len([f for f in findings if f.severity == 'p1'])} important, "
            f"{len([f for f in findings if f.severity == 'p2'])} advisory."
        ),
        registry_root=_root_label(worktree, registry_root),
        registry_count=len(registry_paths),
        entry_count=entry_count,
        findings=findings,
        recommendations=_recommendations(findings),
    )


def render_ecosystem_quality_report(report: EcosystemQualityReport) -> str:
    lines = [
        "# Ecosystem Quality Audit",
        "",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        f"Registry root: {report.registry_root}",
        "",
        report.summary,
        "",
        "This audit checks whether skill and plugin registry entries are precise enough for automatic routing, safe enough for Mode A handoffs, and ready for evidence-backed self-evolution.",
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No quality findings.")
    for finding in report.findings:
        lines.append(
            f"- [{finding.severity.upper()}][{finding.kind}:{finding.name}][{finding.area}] {finding.summary}"
        )
        lines.append(f"  Next: {finding.recommendation}")
        if finding.evidence:
            lines.append(f"  Evidence: {', '.join(finding.evidence)}")
    lines.extend(["", "## Recommendations", _bullets(report.recommendations)])
    return "\n".join(lines) + "\n"


def _entry_findings(kind: str, name: str, entry: dict[str, Any]) -> list[EcosystemQualityFinding]:
    findings: list[EcosystemQualityFinding] = []
    label = _text(entry.get("label", ""))
    description = _text(entry.get("description", ""))
    use_when = _strings(entry.get("use_when", []))
    phases = _strings(entry.get("phases", []))
    command_hint = _text(entry.get("command_hint", ""))
    risk = _text(entry.get("risk", "low")).lower()
    requires_user_approval = bool(entry.get("requires_user_approval", False))

    if len(description) < 24:
        findings.append(
            _finding(
                "p1",
                kind,
                name,
                "routing",
                "Description is too short to route reliably.",
                "Add a concrete description of the task, context, and expected outcome.",
                [f"description={description or 'missing'}"],
            )
        )
    if len(use_when) < 2:
        findings.append(
            _finding(
                "p1",
                kind,
                name,
                "routing",
                "Routing keywords are missing or too sparse.",
                "Add two or more specific `use_when` terms that match real goal language.",
                [f"use_when={use_when or 'missing'}"],
            )
        )
    elif all(term in BROAD_TERMS for term in use_when):
        findings.append(
            _finding(
                "p1",
                kind,
                name,
                "routing",
                "Routing keywords are too broad for automatic selection.",
                "Replace broad terms with specific goal, phase, or domain language.",
                [f"use_when={use_when}"],
            )
        )
    if use_when and not _has_semantic_overlap(label, description, command_hint, use_when):
        findings.append(
            _finding(
                "p1",
                kind,
                name,
                "routing",
                "Routing keywords do not match the label, description, or command hint.",
                "Align `use_when` with the tool's actual purpose so agents can explain the match.",
                [f"use_when={use_when}"],
            )
        )
    if risk not in VALID_RISKS:
        findings.append(
            _finding(
                "p0",
                kind,
                name,
                "safety",
                "Risk must be one of low, medium, or high.",
                "Set `risk` to low, medium, or high before this entry is used.",
                [f"risk={risk or 'missing'}"],
            )
        )
    if kind == "plugin" and risk == "high" and not requires_user_approval:
        findings.append(
            _finding(
                "p0",
                kind,
                name,
                "safety",
                "High-risk plugins must require user approval.",
                "Set `requires_user_approval: true` or lower the risk with evidence.",
                ["risk=high", "requires_user_approval=false"],
            )
        )
    if command_hint and any(pattern.search(command_hint) for pattern in LOCAL_PATH_PATTERNS):
        findings.append(
            _finding(
                "p0",
                kind,
                name,
                "safety",
                "Command hint contains a local filesystem path.",
                "Replace local paths with portable commands or placeholders before publishing.",
                ["command_hint contains local path"],
            )
        )
    if not phases:
        findings.append(
            _finding(
                "p2",
                kind,
                name,
                "routing",
                "No phase hints are recorded.",
                "Add likely phases such as P1, P2, P3, or P4 to improve recommendations.",
                [],
            )
        )
    if not command_hint:
        findings.append(
            _finding(
                "p2",
                kind,
                name,
                "validation",
                "No command or usage hint is recorded.",
                "Add a portable command hint or short usage instruction.",
                [],
            )
        )
    return findings


def _finding(
    severity: str,
    kind: str,
    name: str,
    area: str,
    summary: str,
    recommendation: str,
    evidence: list[str],
) -> EcosystemQualityFinding:
    return EcosystemQualityFinding(
        severity=severity,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        name=name,
        area=area,  # type: ignore[arg-type]
        summary=summary,
        recommendation=recommendation,
        evidence=evidence,
    )


def _registry_root(worktree: Path) -> Path:
    if (worktree / "registries").exists():
        return worktree / "registries"
    return Path(__file__).resolve().parents[2] / "registries"


def _root_label(worktree: Path, registry_root: Path) -> str:
    try:
        if registry_root.resolve().is_relative_to(worktree.resolve()):
            return "project registries"
    except OSError:
        pass
    return "built-in registries"


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item).lower() for item in value if _text(item)]
    if isinstance(value, str):
        return [value.lower()]
    return []


def _text(value: Any) -> str:
    return str(value).strip()


def _has_semantic_overlap(
    label: str, description: str, command_hint: str, use_when: list[str]
) -> bool:
    haystack = set(_tokens(" ".join([label, description, command_hint])))
    needles = set()
    for term in use_when:
        needles.update(_tokens(term))
    return bool(haystack & needles)


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]


def _recommendations(findings: list[EcosystemQualityFinding]) -> list[str]:
    if not findings:
        return [
            "Keep registry entries reviewed as goal families and local agent ecosystems change.",
            "Use self-evolution memory to decide when a skill should be improved or split.",
            "For deeper optimization, run a SkillOpt-style loop: collect scored rollouts, propose bounded skill edits, and accept only validation-gated improvements.",
        ]
    return [
        "Fix P0/P1 findings before relying on automatic skill or plugin routing.",
        "Treat repeated routing misses as evidence for improving a skill, registry entry, or validation gate.",
        "Use bounded, validation-gated edits for reusable skills instead of broad prompt rewrites.",
    ]


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
