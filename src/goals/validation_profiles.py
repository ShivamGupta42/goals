"""Validation profiles for reusable loop proof rules.

Profiles are intentionally shallow at the durable interface: loop phases store
only profile names. This module is the deep implementation behind that seam: it
loads known profile definitions, expands their reusable proof requirements into a
``LoopDesign`` when requested, and lets the linter flag unknown profile names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from goals.loop_builder import LoopDesign
from goals.storage import GoalsError


class ValidationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    label: str
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    termination_conditions: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class ProfileExpansionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design: LoopDesign
    applied: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "generic": {
        "label": "Generic project",
    },
    "web-app": {
        "label": "Web app",
    },
    "product-ux-review": {
        "label": "Product UX review",
        "description": "Browser-visible product work needs proof that the user task works.",
        "acceptance_criteria": [
            "Evidence is recorded from a user-visible review of the affected experience.",
        ],
    },
    "imported-loop": {
        "label": "Imported loop",
        "description": "A loop imported from a catalog or external source.",
        "acceptance_criteria": [
            "Evidence is recorded against the imported loop step before this phase is accepted.",
        ],
        "termination_conditions": [
            "The imported loop stop condition is satisfied or an explicit blocker is recorded.",
        ],
    },
    "benchmark-loop": {
        "label": "Benchmark loop",
        "description": "Baseline, compare, and keep only verified improvements.",
        "acceptance_criteria": [
            "The baseline and current measurement use the same documented method.",
            "Evidence records the measured result and whether it regressed.",
        ],
    },
    "browser-ux-loop": {
        "label": "Browser UX loop",
        "description": "Browser or screenshot based verification for user-facing loops.",
        "acceptance_criteria": [
            "Browser or screenshot evidence is recorded for the affected user-visible state.",
            "Any untested screen size, mode, or interaction remains an explicit known gap.",
        ],
    },
    "experiment-loop": {
        "label": "Experiment loop",
        "description": "Comparable candidate runs with guard-safe promotion.",
        "acceptance_criteria": [
            "Candidate results are compared against the same evaluation conditions.",
            "Promotion, rollback, or stop reason is recorded with evidence.",
        ],
    },
    "repository-maintenance-loop": {
        "label": "Repository maintenance loop",
        "description": "Repository cleanup, branch, or release work with local proof.",
        "acceptance_criteria": [
            "Repository state was inspected before changing files.",
            "Relevant tests or checks are recorded after the retained change.",
        ],
    },
}


def load_validation_profiles(root: Path | None = None) -> dict[str, ValidationProfile]:
    """Load built-in profiles plus optional project ``registries/profiles.yml``.

    Project entries override built-ins by id. The package can run without a
    checked-out repo because the built-ins live in code; the registry remains the
    extension point for project-specific proof rules.
    """
    profiles = _profiles_from_mapping(BUILTIN_PROFILES)
    path = (root or Path.cwd()) / "registries" / "profiles.yml"
    if not path.exists():
        return profiles
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or data.get("kind") != "profiles":
        raise GoalsError(f"{path} must be a profiles registry.")
    raw_profiles = data.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raise GoalsError(f"{path} field profiles must contain a mapping.")
    profiles.update(_profiles_from_mapping(raw_profiles))
    return profiles


def apply_validation_profiles(
    design: LoopDesign,
    *,
    profiles: dict[str, ValidationProfile] | None = None,
    root: Path | None = None,
) -> ProfileExpansionResult:
    """Return a copy of ``design`` with profile requirements materialized.

    Expansion is explicit and idempotent. It keeps profile names on phases while
    appending each known profile's reusable acceptance criteria, termination
    conditions, and skill references when missing.
    """
    known = profiles if profiles is not None else load_validation_profiles(root)
    expanded = design.model_copy(deep=True)
    applied: list[str] = []
    missing: list[str] = []
    for phase in expanded.phases:
        for profile_name in phase.validation_profiles:
            profile = known.get(profile_name)
            if profile is None:
                missing.append(f"{phase.phase_id}:{profile_name}")
                continue
            for criterion in profile.acceptance_criteria:
                if criterion not in phase.acceptance_criteria:
                    phase.acceptance_criteria.append(criterion)
                    applied.append(f"{phase.phase_id}:{profile_name}:acceptance")
            for condition in profile.termination_conditions:
                if condition not in phase.termination_conditions:
                    phase.termination_conditions.append(condition)
                    applied.append(f"{phase.phase_id}:{profile_name}:termination")
            for skill in profile.skills:
                if skill not in phase.skills:
                    phase.skills.append(skill)
                    applied.append(f"{phase.phase_id}:{profile_name}:skill")
    return ProfileExpansionResult(design=expanded, applied=applied, missing=missing)


def _profiles_from_mapping(raw_profiles: dict[str, Any]) -> dict[str, ValidationProfile]:
    profiles: dict[str, ValidationProfile] = {}
    for profile_id, entry in raw_profiles.items():
        if not isinstance(entry, dict):
            raise GoalsError(f"Profile {profile_id} must contain a mapping.")
        data = dict(entry)
        data["profile_id"] = str(profile_id)
        try:
            profiles[str(profile_id)] = ValidationProfile.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            raise GoalsError(f"Invalid validation profile {profile_id}: {exc}") from exc
    return profiles
