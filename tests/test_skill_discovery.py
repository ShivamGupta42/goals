from pathlib import Path

from goals.skill_discovery import DiscoveredSkill, discover_skills


def _write_skill(root: Path, name: str, description: str = "Does a thing.") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return skill_dir


def _discover(tmp_path: Path) -> list[DiscoveredSkill]:
    return discover_skills(
        claude_dir=tmp_path / "claude",
        codex_dir=tmp_path / "codex",
        bundled_dir=tmp_path / "bundled",
    )


def test_per_source_attribution(tmp_path: Path) -> None:
    _write_skill(tmp_path / "claude", "claude-only")
    _write_skill(tmp_path / "codex", "codex-only")
    _write_skill(tmp_path / "bundled", "goals-bundled")

    skills = {s.name: s for s in _discover(tmp_path)}

    assert skills["claude-only"].agents == ["claude"]
    assert skills["claude-only"].sources == ["claude"]
    assert skills["codex-only"].agents == ["codex"]
    # Bundled-only skills exist but no agent natively invokes them yet.
    assert skills["goals-bundled"].agents == []
    assert skills["goals-bundled"].sources == ["bundled"]


def test_present_in_both_unions_and_uses_claude_precedence(tmp_path: Path) -> None:
    _write_skill(tmp_path / "claude", "shared", description="From Claude.")
    _write_skill(tmp_path / "codex", "shared", description="From Codex.")

    shared = {s.name: s for s in _discover(tmp_path)}["shared"]

    assert shared.agents == ["claude", "codex"]
    assert shared.sources == ["claude", "codex"]
    # claude wins the displayed description (precedence claude > codex > bundled).
    assert shared.description == "From Claude."
    assert "/claude/" in shared.path


def test_top_level_only_ignores_nested_subskills(tmp_path: Path) -> None:
    # A bundle whose own sub-skills live deeper must not surface as top-level.
    parent = _write_skill(tmp_path / "claude", "product-design")
    nested = parent / "skills" / "index"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text("---\nname: index\ndescription: x\n---\n", encoding="utf-8")

    names = {s.name for s in _discover(tmp_path)}

    assert "product-design" in names
    assert "index" not in names


def test_skips_readme_dotdirs_and_dirs_without_skill_md(tmp_path: Path) -> None:
    claude = tmp_path / "claude"
    _write_skill(claude, "real-skill")
    (claude / "README.md").write_text("not a skill", encoding="utf-8")
    (claude / ".system").mkdir(parents=True)
    (claude / ".system" / "SKILL.md").write_text("---\nname: sys\ndescription: x\n---\n")
    (claude / "empty-dir").mkdir()

    names = {s.name for s in _discover(tmp_path)}

    assert names == {"real-skill"}


def test_malformed_frontmatter_is_skipped(tmp_path: Path) -> None:
    claude = tmp_path / "claude"
    _write_skill(claude, "good")
    # no frontmatter fences
    (claude / "no-fence").mkdir(parents=True)
    (claude / "no-fence" / "SKILL.md").write_text("# just a heading\n", encoding="utf-8")
    # broken yaml
    (claude / "bad-yaml").mkdir(parents=True)
    (claude / "bad-yaml" / "SKILL.md").write_text("---\nname: : :\n---\n", encoding="utf-8")
    # missing name
    (claude / "no-name").mkdir(parents=True)
    (claude / "no-name" / "SKILL.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")

    names = {s.name for s in _discover(tmp_path)}

    assert names == {"good"}


def test_missing_source_dir_is_skipped(tmp_path: Path) -> None:
    # Only codex exists; claude and bundled dirs are absent.
    _write_skill(tmp_path / "codex", "lonely")

    skills = _discover(tmp_path)

    assert [s.name for s in skills] == ["lonely"]


def test_results_are_deterministically_sorted(tmp_path: Path) -> None:
    for name in ["zebra", "alpha", "mango"]:
        _write_skill(tmp_path / "claude", name)

    names = [s.name for s in _discover(tmp_path)]

    assert names == ["alpha", "mango", "zebra"]
