from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from goals.adapters import adapter_check
from goals.models import DiscoveredTool, EcosystemDiscoveryReport


def discover_local_ecosystem(
    worktree: Path,
    *,
    skill_roots: list[Path] | None = None,
    max_skills: int = 200,
) -> EcosystemDiscoveryReport:
    registry_names = _registry_names(worktree)
    tools: list[DiscoveredTool] = []
    tools.extend(_discover_adapters(registry_names))
    tools.extend(
        _discover_skills(skill_roots or default_skill_roots(worktree), registry_names, max_skills)
    )
    tools.sort(key=lambda item: (item.kind, item.name))
    missing = [tool for tool in tools if not tool.registered]
    return EcosystemDiscoveryReport(
        tools=tools,
        missing_from_registry=missing,
        summary=(
            f"Discovered {len(tools)} local tool(s); "
            f"{len(missing)} not represented in portable registries."
        ),
    )


def render_discovery_report(report: EcosystemDiscoveryReport) -> str:
    if not report.tools:
        return f"{report.summary}\n- No local skills or adapters discovered."
    lines = [report.summary]
    for tool in report.tools:
        status = "registered" if tool.registered else "missing from registry"
        detail = f"- {tool.kind}: {tool.name} ({tool.label}) - {status}"
        if tool.description:
            detail += f". {tool.description}"
        if tool.source:
            detail += f" Source: {tool.source}."
        lines.append(detail)
    if report.missing_from_registry:
        lines.append("Suggested registry additions:")
        for tool in report.missing_from_registry[:10]:
            lines.append(f"- {tool.kind}: {tool.name} -> {tool.suggested_registry_entry}")
    return "\n".join(lines)


def default_skill_roots(worktree: Path) -> list[Path]:
    env = os.environ.get("GOALS_SKILL_ROOTS")
    if env:
        return [Path(item).expanduser() for item in env.split(os.pathsep) if item]
    home = Path.home()
    return [
        worktree / ".claude" / "skills",
        worktree / ".codex" / "skills",
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
    ]


def _discover_adapters(registry_names: dict[str, set[str]]) -> list[DiscoveredTool]:
    tools = []
    for name in ("claude", "codex"):
        exists = shutil.which(name) is not None
        ready, detail = adapter_check(name) if exists else (False, f"{name} executable not found.")
        tools.append(
            DiscoveredTool(
                kind="adapter",
                name=name,
                label=f"{name.title()} adapter",
                description=_safe_detail(detail),
                source="PATH",
                registered=name in registry_names["adapters"],
                available=ready,
                registry="adapters.yml",
                suggested_registry_entry={
                    name: {
                        "label": f"{name.title()} native goal adapter",
                    }
                },
            )
        )
    return tools


def _discover_skills(
    roots: list[Path],
    registry_names: dict[str, set[str]],
    max_skills: int,
) -> list[DiscoveredTool]:
    tools: list[DiscoveredTool] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            if len(tools) >= max_skills:
                return tools
            meta = _read_skill_metadata(skill_file)
            name = _slug(meta.get("name") or skill_file.parent.name)
            if name in seen:
                continue
            seen.add(name)
            label = str(meta.get("name") or skill_file.parent.name).strip()
            description = _first_sentence(str(meta.get("description", "")).strip())
            tools.append(
                DiscoveredTool(
                    kind="skill",
                    name=name,
                    label=label,
                    description=description,
                    source=_source_label(root),
                    registered=name in registry_names["skills"],
                    registry="skills.yml",
                    suggested_registry_entry={
                        name: {
                            "label": label,
                            "description": description or f"Use the local {label} skill.",
                            "use_when": _use_when_terms(name, description),
                            "risk": "low",
                            "requires_user_approval": False,
                        }
                    },
                )
            )
    return tools


def _registry_names(worktree: Path) -> dict[str, set[str]]:
    root = worktree / "registries"
    if not root.exists():
        root = Path(__file__).resolve().parents[2] / "registries"
    return {
        "skills": _names_from_registry(root / "skills.yml", "skills"),
        "plugins": _names_from_registry(root / "plugins.yml", "plugins"),
        "adapters": _names_from_registry(root / "adapters.yml", "adapters"),
    }


def _names_from_registry(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get(key, {})
    return {_slug(str(name)) for name in entries} if isinstance(entries, dict) else set()


def _read_skill_metadata(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            data = yaml.safe_load(parts[1]) or {}
            return data if isinstance(data, dict) else {}
    metadata: dict[str, Any] = {}
    for line in text.splitlines()[:20]:
        if line.startswith("# ") and "name" not in metadata:
            metadata["name"] = line[2:].strip()
        elif line.lower().startswith("description:"):
            metadata["description"] = line.split(":", 1)[1].strip()
    return metadata


def _source_label(root: Path) -> str:
    home = Path.home()
    try:
        relative = root.expanduser().resolve().relative_to(home.resolve())
        return f"home:{relative}"
    except ValueError:
        parts = root.parts[-3:]
        return "local:" + "/".join(parts)


def _safe_detail(detail: str) -> str:
    home = str(Path.home())
    return detail.replace(home, "~")[:160]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "tool"


def _first_sentence(value: str) -> str:
    return re.split(r"(?<=[.!?])\s+", value, maxsplit=1)[0][:180]


def _use_when_terms(name: str, description: str) -> list[str]:
    terms = [
        term for term in re.findall(r"[a-z0-9]+", f"{name} {description}".lower()) if len(term) > 3
    ]
    result = []
    for term in terms:
        if term not in result:
            result.append(term)
    return result[:8]
