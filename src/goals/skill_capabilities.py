from __future__ import annotations

import shutil
from pathlib import Path

from goals.models import SkillCapabilityFinding, SkillCapabilityReport
from goals.skill_discovery import DiscoveredSkill, discover_skills
from goals.storage import GoalsError


CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "frontend-build": ("website", "frontend", "landing", "ui", "web app", "dashboard"),
    "frontend-render-validation": ("browser", "render", "responsive", "overflow", "screenshot"),
    "product-ux-review": ("ux", "jtbd", "product", "conversion", "copy", "landing"),
    "security-review": ("auth", "security", "permission", "payment", "stripe", "secret"),
    "skill-authoring": ("skill", "skills", "codex skill", "claude skill"),
    "goal-workflow": ("goal", "workflow", "phase", "evidence", "loop"),
}


def infer_capabilities(objective: str) -> list[str]:
    text = objective.lower()
    found = [
        capability
        for capability, needles in CAPABILITY_KEYWORDS.items()
        if any(needle in text for needle in needles)
    ]
    if not found:
        found.append("goal-workflow")
    return sorted(set(found))


def analyze_skill_capabilities(
    objective: str,
    *,
    skills: list[DiscoveredSkill] | None = None,
    quarantined_root: Path | None = None,
) -> SkillCapabilityReport:
    discovered = skills if skills is not None else discover_skills()
    root = quarantined_root if quarantined_root is not None else Path.cwd() / ".goals" / "quarantined-skills"
    findings = [
        _finding_for_capability(capability, discovered, root)
        for capability in infer_capabilities(objective)
    ]
    blocking = [finding for finding in findings if finding.status != "installed"]
    return SkillCapabilityReport(
        objective=objective,
        passed=not blocking,
        summary=(
            f"{len(findings)} needed capability/capabilities: "
            f"{len(blocking)} need action."
        ),
        findings=findings,
        user_choices=[
            "Install or copy a trusted skill into ~/.codex/skills or ~/.claude/skills.",
            "Create a repo-local skill and commit it with the project.",
            "Continue with an explicit skill-gap waiver recorded as goal evidence or a decision.",
        ],
    )


def quarantine_skill(source: Path, name: str, *, root: Path | None = None) -> Path:
    if not source.exists():
        raise GoalsError(f"Skill source not found: {source}")
    if not source.is_dir():
        raise GoalsError(f"Skill source must be a directory: {source}")
    if not (source / "SKILL.md").is_file():
        raise GoalsError(f"Skill source has no SKILL.md: {source}")
    safe_name = _safe_name(name or source.name)
    if not safe_name:
        raise GoalsError("Skill name must contain at least one letter or number.")
    target_root = root if root is not None else Path.cwd() / ".goals" / "quarantined-skills"
    target = target_root / safe_name
    if target.exists():
        raise GoalsError(f"Quarantined skill already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=False)
    return target


def render_skill_capability_report(report: SkillCapabilityReport) -> str:
    lines = [
        "# Skill Capability Preflight",
        "",
        f"Objective: {report.objective}",
        f"Overall: {'pass' if report.passed else 'needs action'}",
        report.summary,
        "",
        "## Capabilities",
    ]
    for finding in report.findings:
        skill = f" ({finding.skill})" if finding.skill else ""
        lines.append(f"- [{finding.status}] {finding.capability}{skill}: {finding.detail}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    lines.extend(["", "## Choices"])
    lines.extend(f"- {choice}" for choice in report.user_choices)
    return "\n".join(lines) + "\n"


def _finding_for_capability(
    capability: str,
    skills: list[DiscoveredSkill],
    quarantined_root: Path,
) -> SkillCapabilityFinding:
    candidates = [skill for skill in skills if capability in _skill_capabilities(skill)]
    if candidates:
        skill = candidates[0]
        if skill.agents:
            status = "installed" if "codex" in skill.agents else "other-agent"
            action = (
                ""
                if status == "installed"
                else f"Copy or install {skill.name} for Codex before relying on it."
            )
            return SkillCapabilityFinding(
                capability=capability,
                status=status,  # type: ignore[arg-type]
                skill=skill.name,
                detail=f"Found in {', '.join(skill.sources)}; agents={', '.join(skill.agents)}.",
                suggested_action=action,
            )
        return SkillCapabilityFinding(
            capability=capability,
            status="bundled-only",
            skill=skill.name,
            detail="Goals bundles this skill, but no native agent auto-discovers it yet.",
            suggested_action="Run `goals skills install --target codex` or install it for your active agent.",
        )
    if _quarantined_has_capability(quarantined_root, capability):
        return SkillCapabilityFinding(
            capability=capability,
            status="quarantined",
            detail="A matching skill appears in .goals/quarantined-skills but is not trusted yet.",
            suggested_action="Review provenance and promote it manually into an agent skill dir.",
        )
    return SkillCapabilityFinding(
        capability=capability,
        status="unknown",
        detail="No discovered skill declares or appears to cover this capability.",
        suggested_action="Pull a trusted skill, create a repo-local skill, or record a waiver.",
    )


def _skill_capabilities(skill: DiscoveredSkill) -> set[str]:
    capabilities = set(skill.capabilities)
    haystack = f"{skill.name} {skill.description}".lower()
    for capability, needles in CAPABILITY_KEYWORDS.items():
        if any(needle in haystack for needle in needles):
            capabilities.add(capability)
    return capabilities


def _quarantined_has_capability(root: Path, capability: str) -> bool:
    if not root.is_dir():
        return False
    needle = capability.replace("-", " ")
    for skill_md in root.glob("*/SKILL.md"):
        try:
            text = skill_md.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        if capability in text or needle in text:
            return True
    return False


def _safe_name(name: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "-" for ch in name.strip()]
    return "-".join(part for part in "".join(chars).split("-") if part)
