from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from goals.discovery import discover_local_ecosystem
from goals.models import RegistrySyncChange, RegistrySyncPlan
from goals.registry import validate_registry_file
from goals.storage import GoalsError, atomic_write_text

REGISTRY_KIND = {"skill": "skills", "plugin": "plugins", "adapter": "adapters"}


def plan_registry_sync(
    worktree: Path,
    *,
    skill_roots: list[Path] | None = None,
    include_adapters: bool = True,
    include_skills: bool = True,
    max_skills: int = 200,
) -> RegistrySyncPlan:
    report = discover_local_ecosystem(worktree, skill_roots=skill_roots, max_skills=max_skills)
    changes = []
    for tool in report.missing_from_registry:
        if tool.kind == "adapter" and not tool.available:
            continue
        if tool.kind == "adapter" and not include_adapters:
            continue
        if tool.kind == "skill" and not include_skills:
            continue
        if tool.kind not in REGISTRY_KIND:
            continue
        entry = tool.suggested_registry_entry.get(tool.name, {})
        changes.append(
            RegistrySyncChange(
                registry=tool.registry,
                kind=tool.kind,
                name=tool.name,
                entry=entry,
            )
        )
    return RegistrySyncPlan(
        changes=changes,
        dry_run=True,
        summary=f"Prepared {len(changes)} registry addition(s) from local discovery.",
    )


def apply_registry_sync(worktree: Path, plan: RegistrySyncPlan) -> RegistrySyncPlan:
    registry_root = worktree / "registries"
    if not registry_root.exists():
        raise GoalsError("No registries directory found.")
    for change in plan.changes:
        _apply_change(registry_root, change)
    return plan.model_copy(
        update={
            "dry_run": False,
            "summary": f"Applied {len(plan.changes)} registry addition(s).",
        }
    )


def render_registry_sync_plan(plan: RegistrySyncPlan) -> str:
    mode = "dry run" if plan.dry_run else "applied"
    if not plan.changes:
        return f"{plan.summary}\n- No registry changes needed."
    lines = [f"{plan.summary} ({mode})"]
    for change in plan.changes:
        lines.append(f"- add {change.kind}: {change.name} to {change.registry} -> {change.entry}")
    return "\n".join(lines)


def _apply_change(registry_root: Path, change: RegistrySyncChange) -> None:
    path = registry_root / change.registry
    data = _load_or_default(path, change.kind)
    collection = REGISTRY_KIND[change.kind]
    entries = data.setdefault(collection, {})
    if not isinstance(entries, dict):
        raise GoalsError(f"{path} field {collection} must contain a mapping.")
    if change.name in entries:
        return
    entries[change.name] = _sanitize_entry(change.entry)
    text = yaml.safe_dump(data, sort_keys=True, allow_unicode=False)
    atomic_write_text(path, text)
    validate_registry_file(path)


def _load_or_default(path: Path, kind: str) -> dict[str, Any]:
    collection = REGISTRY_KIND[kind]
    if not path.exists():
        return {"version": 1, "kind": collection, collection: {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise GoalsError(f"{path} must contain a mapping.")
    if data.get("kind") != collection:
        raise GoalsError(f"{path} must be a {collection} registry.")
    return data


def _sanitize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(entry)
    for key in ("description", "label", "command_hint"):
        if key in sanitized:
            sanitized[key] = str(sanitized[key]).replace(str(Path.home()), "~")
    return sanitized
