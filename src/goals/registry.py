from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from goals.storage import GoalsError

ALLOWED_KEYS = {
    "profiles": {"version", "kind", "profiles"},
    "skills": {"version", "kind", "skills"},
    "gates": {"version", "kind", "gates"},
    "agents": {"version", "kind", "agents"},
    "adapters": {"version", "kind", "adapters"},
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
