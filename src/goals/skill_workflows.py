from __future__ import annotations

from pathlib import Path

from goals.models import SkillCapabilityReport
from goals.skill_capabilities import analyze_skill_capabilities, quarantine_skill
from goals.skill_discovery import DiscoveredSkill, SkillInstallReport, discover_skills, install_bundled_skills


def list_skills() -> list[DiscoveredSkill]:
    return discover_skills()


def install_skills(targets: list[str], *, force: bool = False) -> SkillInstallReport:
    return install_bundled_skills(targets, force=force)


def preflight_skills(objective: str) -> SkillCapabilityReport:
    return analyze_skill_capabilities(objective)


def import_skill(source: Path, name: str = "") -> Path:
    return quarantine_skill(source, name)
