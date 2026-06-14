"""Live discovery of agent skills from SKILL.md files.

Goals does not maintain a registry of skills. It discovers them at runtime from
the agents' own skill directories plus the skills it ships itself. This is the
single source of truth for "what skills exist," replacing the old static
``registries/skills.yml`` catalog.
"""

from __future__ import annotations

from pathlib import Path

CLAUDE_SKILLS_DIR = Path.home() / ".claude" / "skills"
CODEX_SKILLS_DIR = Path.home() / ".codex" / "skills"


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
