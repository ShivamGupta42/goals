from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from goals.storage import GoalsError

ALLOWED_KEYS = {
    "profiles": {"version", "kind", "profiles"},
    "gates": {"version", "kind", "gates"},
    "agents": {"version", "kind", "agents"},
    "adapters": {"version", "kind", "adapters"},
    "permissions": {"version", "kind", "permissions"},
}

ENTRY_KEYS = {
    "adapters": {
        "label",
    },
    "permissions": {
        "label",
        "description",
        "match",
        "decision",
        "risk",
        "user_question",
        "agent_action",
    },
    "profiles": {
        "label",
        "description",
        "acceptance_criteria",
        "termination_conditions",
        "skills",
    },
}


def validate_registry_file(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise GoalsError(f"{path} must contain a mapping.")
    kind = data.get("kind")
    if kind not in ALLOWED_KEYS:
        raise GoalsError(f"{path} has unknown registry kind: {kind}")
    extra = set(data) - ALLOWED_KEYS[kind]
    if extra:
        raise GoalsError(f"{path} has unknown critical fields: {sorted(extra)}")
    if "version" not in data:
        raise GoalsError(f"{path} must include version.")
    if kind in ENTRY_KEYS:
        _validate_entries(path, data, kind)
    return data


def validate_registries(root: Path) -> list[Path]:
    registry_root = root / "registries"
    if not registry_root.exists():
        return []
    validated = []
    for path in sorted(registry_root.glob("*.yml")):
        validate_registry_file(path)
        validated.append(path)
    return validated


def _validate_entries(path: Path, data: dict[str, Any], kind: str) -> None:
    entries = data.get(kind, {})
    if not isinstance(entries, dict):
        raise GoalsError(f"{path} field {kind} must contain a mapping.")
    allowed = ENTRY_KEYS[kind]
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise GoalsError(f"{path} entry {name} must contain a mapping.")
        extra = set(entry) - allowed
        if extra:
            raise GoalsError(f"{path} entry {name} has unknown critical fields: {sorted(extra)}")
        if "label" not in entry:
            raise GoalsError(f"{path} entry {name} must include label.")
