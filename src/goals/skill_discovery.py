"""Live discovery of agent skills from SKILL.md files.

Goals does not maintain a registry of skills. It discovers them at runtime from
the agents' own skill directories plus the skills it ships itself. This is the
single source of truth for "what skills exist," replacing the old static
``registries/skills.yml`` catalog.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

CLAUDE_SKILLS_DIR = Path.home() / ".claude" / "skills"
CODEX_SKILLS_DIR = Path.home() / ".codex" / "skills"

# Install targets — where the optional `goals skills install` copies bundled
# skills so a native agent can invoke them directly.
TARGET_DIRS = {"claude": CLAUDE_SKILLS_DIR, "codex": CODEX_SKILLS_DIR}

_MAX_DESCRIPTION = 120

# Source labels and their precedence when the same skill appears in several
# places (lowest wins for the displayed description/path).
_SOURCE_PRECEDENCE = {"claude": 0, "codex": 1, "bundled": 2}
# Sources that correspond to an agent that natively auto-discovers the skill.
# "bundled" is goals' own package dir — no agent reads it until it is installed.
_AGENT_SOURCES = {"claude", "codex"}


class DiscoveredSkill(BaseModel):
    """A skill found by scanning SKILL.md files.

    ``name`` is the skill's directory name (the canonical identity used for
    dedupe). ``sources`` is where it was found; ``agents`` is the subset of
    sources an agent natively invokes (so an empty ``agents`` means "exists but
    no agent auto-discovers it yet").
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    sources: list[str]
    agents: list[str]
    path: str


class SkillInstallResult(BaseModel):
    """Outcome of installing one bundled skill into one target dir.

    ``status`` is one of: ``installed`` (newly copied), ``current`` (already
    present and identical), ``overwritten`` (replaced under ``--force``), or
    ``blocked`` (a differing same-named skill exists; left untouched to avoid
    clobbering something we did not create).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    status: str


class SkillInstallReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[SkillInstallResult]


def bundled_skills_root() -> Path:
    """Locate goals' own bundled skills.

    Prefers the packaged location (``goals/bundled_skills`` inside the installed
    package, placed there by the hatch ``force-include`` mapping). Falls back to
    the repo-root ``skills/`` directory for editable/dev installs. The packaged
    check comes first so the fragile parents[] path is only ever the dev
    fallback — avoiding the wheel-path bug the old registries loader had.
    """
    package_dir = Path(__file__).resolve().parent  # .../goals
    packaged = package_dir / "bundled_skills"
    if packaged.is_dir():
        return packaged
    return package_dir.parents[1] / "skills"  # repo-root/skills (editable/dev)


def discover_skills(
    *,
    claude_dir: Path | None = None,
    codex_dir: Path | None = None,
    bundled_dir: Path | None = None,
) -> list[DiscoveredSkill]:
    """Scan the three skill sources and return deduped, sorted skills.

    Dirs are overridable for testing. Scanning is top-level only
    (``<source>/<dir>/SKILL.md``) — sub-skills nested deeper are ignored. A
    missing source dir is skipped; a malformed or nameless ``SKILL.md`` is
    skipped without raising.
    """
    sources: list[tuple[str, Path]] = [
        ("claude", claude_dir if claude_dir is not None else CLAUDE_SKILLS_DIR),
        ("codex", codex_dir if codex_dir is not None else CODEX_SKILLS_DIR),
        ("bundled", bundled_dir if bundled_dir is not None else bundled_skills_root()),
    ]

    # dir_name -> {source_label: (description, skill_md_path)}
    merged: dict[str, dict[str, tuple[str, Path]]] = {}
    for label, root in sources:
        for dir_name, (description, path) in _scan_source(root).items():
            merged.setdefault(dir_name, {})[label] = (description, path)

    skills: list[DiscoveredSkill] = []
    for dir_name in sorted(merged):
        by_label = merged[dir_name]
        best = min(by_label, key=lambda label: _SOURCE_PRECEDENCE[label])
        description, path = by_label[best]
        present = set(by_label)
        skills.append(
            DiscoveredSkill(
                name=dir_name,
                description=description,
                sources=sorted(present, key=lambda label: _SOURCE_PRECEDENCE[label]),
                agents=sorted(present & _AGENT_SOURCES),
                path=str(path),
            )
        )
    return skills


def _scan_source(root: Path) -> dict[str, tuple[str, Path]]:
    """Return {dir_name: (description, skill_md_path)} for one source dir."""
    found: dict[str, tuple[str, Path]] = {}
    if not root.is_dir():
        return found
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        parsed = _parse_skill_md(skill_md)
        if parsed is None:
            continue
        found[entry.name] = (parsed[1], skill_md)
    return found


def _parse_skill_md(path: Path) -> tuple[str, str] | None:
    """Return (name, description) from SKILL.md frontmatter, or None if invalid."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.lstrip().startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    description = data.get("description", "")
    if not isinstance(description, str):
        description = str(description)
    return name.strip(), description.strip()


def install_bundled_skills(
    targets: list[str],
    *,
    force: bool = False,
    bundled_dir: Path | None = None,
    target_dirs: dict[str, Path] | None = None,
) -> SkillInstallReport:
    """Copy goals' bundled skills into the chosen agent dir(s).

    Collision-safe: a same-named skill that already exists and differs is left
    untouched (``blocked``) unless ``force`` is set — overwriting a user's own
    skill would be data loss. Assumes an unpacked install (the module already
    relies on a filesystem layout via ``Path(__file__)``), which is always the
    case for ``uv``/``pip`` installs.
    """
    bundled = bundled_dir if bundled_dir is not None else bundled_skills_root()
    dirs = target_dirs if target_dirs is not None else TARGET_DIRS
    src_skills = (
        sorted(p for p in bundled.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
        if bundled.is_dir()
        else []
    )

    results: list[SkillInstallResult] = []
    for target in targets:
        root = dirs[target]
        for src in src_skills:
            dest = root / src.name
            if not dest.exists():
                root.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dest)
                status = "installed"
            elif _same_tree(src, dest):
                status = "current"
            elif force:
                shutil.rmtree(dest)
                shutil.copytree(src, dest)
                status = "overwritten"
            else:
                status = "blocked"
            results.append(SkillInstallResult(name=src.name, target=target, status=status))
    return SkillInstallReport(results=results)


def render_skills_list(skills: list[DiscoveredSkill]) -> str:
    if not skills:
        return "No skills discovered in ~/.claude/skills, ~/.codex/skills, or bundled."
    lines = []
    for skill in skills:
        agents = ", ".join(skill.agents) if skill.agents else "not installed (bundled)"
        description = skill.description
        if len(description) > _MAX_DESCRIPTION:
            description = description[: _MAX_DESCRIPTION - 1].rstrip() + "…"
        lines.append(f"- {skill.name} [{agents}] — {description}")
    return "\n".join(lines)


def render_install_report(report: SkillInstallReport) -> str:
    if not report.results:
        return "No bundled skills to install."
    lines = [f"- {r.target}: {r.name} — {r.status}" for r in report.results]
    blocked = [r for r in report.results if r.status == "blocked"]
    if blocked:
        lines.append(
            "Note: blocked skills already exist and differ from goals' copy; "
            "rerun with --force to overwrite (this replaces your version)."
        )
    return "\n".join(lines)


def _same_tree(left: Path, right: Path) -> bool:
    """True if two skill directories have identical files and content."""
    left_files = {p.relative_to(left) for p in left.rglob("*") if p.is_file()}
    right_files = {p.relative_to(right) for p in right.rglob("*") if p.is_file()}
    if left_files != right_files:
        return False
    return all((left / rel).read_bytes() == (right / rel).read_bytes() for rel in left_files)
