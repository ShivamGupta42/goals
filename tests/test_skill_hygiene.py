from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import yaml
from typer.main import get_command

from goals.cli import app

REPO = Path(__file__).resolve().parents[1]
FRONTMATTER_FENCE_RE = re.compile(r"(?m)^---[ \t]*$")
GOALS_REF_RE = re.compile(r"(?<![\w/-])goals(?=\s|`|$)(?:\s+[^`\n]+)?")
TOKEN_TRAILING_PUNCTUATION = ".,:;)]}"


def test_bundled_skill_frontmatter_matches_directory() -> None:
    for skill_dir in _skill_dirs():
        skill_md = skill_dir / "SKILL.md"
        data = _frontmatter(skill_md)

        assert data.get("name") == skill_dir.name, f"{skill_md} name must match folder"
        description = data.get("description")
        assert isinstance(description, str) and description.strip(), (
            f"{skill_md} needs a non-empty description"
        )
        assert set(data) <= {"name", "description"}, (
            f"{skill_md} frontmatter should contain only name and description"
        )


def test_goals_command_references_resolve_to_cli_commands() -> None:
    command_root = get_command(app)
    failures: list[str] = []

    for path in _command_reference_files():
        for line_no, reference in _goals_references(path):
            if _command_path(reference, command_root) is None:
                failures.append(f"{path}:{line_no}: {reference}")

    assert failures == []


def test_command_reference_linter_rejects_bad_nested_subcommands() -> None:
    command_root = get_command(app)

    assert _command_path("goals loop improve --apply", command_root) == ("loop", "improve")
    assert _command_path("goals loop improv --apply", command_root) is None


def _skill_dirs() -> list[Path]:
    return sorted(
        path
        for path in (REPO / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = FRONTMATTER_FENCE_RE.split(text, maxsplit=2)
    assert len(parts) >= 3 and not parts[0].strip(), f"{path} needs YAML frontmatter"
    data = yaml.safe_load(parts[1])
    assert isinstance(data, dict), f"{path} frontmatter must be a mapping"
    return data


def _command_reference_files() -> list[Path]:
    files = list((REPO / "commands").glob("*.md"))
    files += list((REPO / "skills").rglob("*.md"))
    return sorted(files)


def _goals_references(path: Path) -> list[tuple[int, str]]:
    refs: list[tuple[int, str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for match in GOALS_REF_RE.finditer(line):
            refs.append((line_no, match.group(0).replace("\\", " ").strip()))
    return refs


def _command_path(reference: str, command_root: Any) -> tuple[str, ...] | None:
    tokens = _tokens(reference)
    if not tokens or tokens[0] != "goals":
        return None

    command = command_root
    path: list[str] = []
    for raw_token in tokens[1:]:
        token = raw_token.strip(TOKEN_TRAILING_PUNCTUATION)
        if not token or _is_argument_token(token):
            break
        commands = getattr(command, "commands", None)
        if commands is None:
            break
        next_command = commands.get(token)
        if next_command is None:
            return None
        path.append(token)
        command = next_command

    return tuple(path) if path else None


def _tokens(reference: str) -> list[str]:
    try:
        return shlex.split(reference, comments=True)
    except ValueError:
        return reference.split()


def _is_argument_token(token: str) -> bool:
    return (
        token.startswith("-")
        or token.startswith("<")
        or token.startswith("$")
        or token in {"...", "|"}
    )
