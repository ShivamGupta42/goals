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
    plugin_roots: list[Path] | None = None,
    max_skills: int = 200,
    max_plugins: int = 100,
) -> EcosystemDiscoveryReport:
    registry_names = _registry_names(worktree)
    tools: list[DiscoveredTool] = []
    tools.extend(_discover_adapters(registry_names))
    skill_locations = default_skill_roots(worktree) if skill_roots is None else skill_roots
    plugin_locations = default_plugin_roots(worktree) if plugin_roots is None else plugin_roots
    tools.extend(_discover_skills(skill_locations, registry_names, max_skills))
    tools.extend(_discover_plugins(plugin_locations, registry_names, max_plugins))
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
        return f"{report.summary}\n- No local skills, plugins, or adapters discovered."
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


def default_plugin_roots(worktree: Path) -> list[Path]:
    env = os.environ.get("GOALS_PLUGIN_ROOTS")
    if env:
        return [Path(item).expanduser() for item in env.split(os.pathsep) if item]
    home = Path.home()
    return [
        worktree / ".claude" / "plugins",
        worktree / ".codex" / "plugins",
        home / ".agents" / "plugins",
        home / ".claude" / "plugins",
        home / ".codex" / "plugins",
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


def _discover_plugins(
    roots: list[Path],
    registry_names: dict[str, set[str]],
    max_plugins: int,
) -> list[DiscoveredTool]:
    tools: list[DiscoveredTool] = []
    seen_names: set[str] = set()
    seen_dirs: set[Path] = set()
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for metadata_file in _plugin_metadata_files(root):
            if len(tools) >= max_plugins:
                return tools
            plugin_dir = _plugin_dir(metadata_file)
            try:
                resolved_dir = plugin_dir.resolve()
            except OSError:
                resolved_dir = plugin_dir
            if resolved_dir in seen_dirs:
                continue
            meta = _read_plugin_metadata(metadata_file)
            name = _plugin_name(meta, metadata_file)
            if name in seen_names:
                continue
            label = _plugin_label(meta, name)
            description = _first_sentence(str(meta.get("description", "")).strip())
            seen_names.add(name)
            seen_dirs.add(resolved_dir)
            tools.append(
                DiscoveredTool(
                    kind="plugin",
                    name=name,
                    label=label,
                    description=description,
                    source=_source_label(root),
                    registered=name in registry_names["plugins"],
                    registry="plugins.yml",
                    suggested_registry_entry={
                        name: {
                            "label": label,
                            "description": description or f"Use the local {label} plugin.",
                            "use_when": _use_when_terms(
                                name, " ".join([description, _metadata_keywords(meta)])
                            ),
                            "command_hint": f"Use the {label} plugin when available.",
                            "risk": "medium",
                            "requires_user_approval": True,
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
            try:
                data = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                data = {}
            return data if isinstance(data, dict) else {}
    metadata: dict[str, Any] = {}
    for line in text.splitlines()[:20]:
        if line.startswith("# ") and "name" not in metadata:
            metadata["name"] = line[2:].strip()
        elif line.lower().startswith("description:"):
            metadata["description"] = line.split(":", 1)[1].strip()
    return metadata


def _plugin_metadata_files(root: Path) -> list[Path]:
    names = {
        "plugin.json": 0,
        "plugin.yml": 1,
        "plugin.yaml": 1,
        "manifest.json": 2,
        "package.json": 3,
    }
    blocked_parts = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.name in names
        and not any(part in blocked_parts for part in path.parts)
    ]
    return sorted(candidates, key=lambda path: (names[path.name], str(path)))


def _plugin_dir(path: Path) -> Path:
    if path.parent.name in {".codex-plugin", ".claude-plugin"}:
        return path.parent.parent
    return path.parent


def _read_plugin_metadata(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix in {".yml", ".yaml"}:
            data = yaml.safe_load(text) or {}
        else:
            data = yaml.safe_load(text) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _plugin_name(meta: dict[str, Any], path: Path) -> str:
    raw = meta.get("name") or meta.get("id") or meta.get("displayName") or _plugin_dir(path).name
    value = str(raw).strip()
    if "/" in value and value.startswith("@"):
        value = value.rsplit("/", 1)[-1]
    return _slug(value)


def _plugin_label(meta: dict[str, Any], name: str) -> str:
    raw = meta.get("displayName") or meta.get("label") or meta.get("title")
    if raw:
        return str(raw).strip()[:80]
    return " ".join(part.capitalize() for part in name.split("-"))


def _metadata_keywords(meta: dict[str, Any]) -> str:
    keywords = meta.get("keywords", [])
    if isinstance(keywords, list):
        return " ".join(str(keyword) for keyword in keywords)
    if isinstance(keywords, str):
        return keywords
    return ""


def _source_label(root: Path) -> str:
    home = Path.home()
    try:
        relative = root.expanduser().resolve().relative_to(home.resolve())
        short = "/".join(relative.parts[-3:])
        return f"home:{short}"
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
