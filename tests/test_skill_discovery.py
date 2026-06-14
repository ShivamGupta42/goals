from pathlib import Path

from goals.skill_discovery import (
    DiscoveredSkill,
    discover_skills,
    install_bundled_skills,
    render_skills_list,
)


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


def test_inline_triple_dash_in_description_is_preserved(tmp_path: Path) -> None:
    skill = tmp_path / "claude" / "dashy"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        '---\nname: dashy\ndescription: "before --- after"\n---\n# body\n', encoding="utf-8"
    )

    found = {s.name: s for s in _discover(tmp_path)}

    assert found["dashy"].description == "before --- after"


def test_non_utf8_skill_md_is_skipped(tmp_path: Path) -> None:
    claude = tmp_path / "claude"
    _write_skill(claude, "good")
    bad = claude / "binary"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_bytes(b"---\nname: \xff\xfe bad\n---\n")

    names = {s.name for s in _discover(tmp_path)}

    assert names == {"good"}


def test_force_overwrite_leaves_no_temp_dirs(tmp_path: Path) -> None:
    bundled, dirs = _bundled_with(tmp_path)
    _write_skill(dirs["claude"], "goals-x", "user's different version")

    install_bundled_skills(["claude"], force=True, bundled_dir=bundled, target_dirs=dirs)

    leftovers = [p.name for p in dirs["claude"].iterdir() if p.name.startswith(".")]
    assert leftovers == []
    assert "Bundled skill" in (dirs["claude"] / "goals-x" / "SKILL.md").read_text()


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


def _bundled_with(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    bundled = tmp_path / "bundled"
    _write_skill(bundled, "goals-x", "Bundled skill.")
    dirs = {"claude": tmp_path / "claude", "codex": tmp_path / "codex"}
    return bundled, dirs


def test_install_writes_skill(tmp_path: Path) -> None:
    bundled, dirs = _bundled_with(tmp_path)

    report = install_bundled_skills(["claude"], bundled_dir=bundled, target_dirs=dirs)

    assert (dirs["claude"] / "goals-x" / "SKILL.md").is_file()
    assert [r.status for r in report.results] == ["installed"]


def test_install_is_idempotent(tmp_path: Path) -> None:
    bundled, dirs = _bundled_with(tmp_path)
    install_bundled_skills(["claude"], bundled_dir=bundled, target_dirs=dirs)

    report = install_bundled_skills(["claude"], bundled_dir=bundled, target_dirs=dirs)

    assert [r.status for r in report.results] == ["current"]


def test_install_refuses_to_clobber_differing_skill(tmp_path: Path) -> None:
    bundled, dirs = _bundled_with(tmp_path)
    # A user's own, different skill already sits at the same name.
    _write_skill(dirs["claude"], "goals-x", "User's own different skill.")

    report = install_bundled_skills(["claude"], bundled_dir=bundled, target_dirs=dirs)

    assert [r.status for r in report.results] == ["blocked"]
    assert "User's own" in (dirs["claude"] / "goals-x" / "SKILL.md").read_text()


def test_install_force_overwrites_differing_skill(tmp_path: Path) -> None:
    bundled, dirs = _bundled_with(tmp_path)
    _write_skill(dirs["claude"], "goals-x", "User's own different skill.")

    report = install_bundled_skills(["claude"], force=True, bundled_dir=bundled, target_dirs=dirs)

    assert [r.status for r in report.results] == ["overwritten"]
    assert "Bundled skill" in (dirs["claude"] / "goals-x" / "SKILL.md").read_text()


def test_install_both_targets(tmp_path: Path) -> None:
    bundled, dirs = _bundled_with(tmp_path)

    report = install_bundled_skills(["claude", "codex"], bundled_dir=bundled, target_dirs=dirs)

    assert sorted(r.target for r in report.results) == ["claude", "codex"]
    assert (dirs["claude"] / "goals-x" / "SKILL.md").is_file()
    assert (dirs["codex"] / "goals-x" / "SKILL.md").is_file()


def test_install_never_follows_or_deletes_a_symlinked_dest(tmp_path: Path) -> None:
    bundled, dirs = _bundled_with(tmp_path)
    # The user's skill slot is a symlink pointing at an external real directory.
    external = tmp_path / "external-target"
    external.mkdir()
    (external / "SKILL.md").write_text("---\nname: goals-x\ndescription: user.\n---\n")
    dirs["claude"].mkdir(parents=True)
    link = dirs["claude"] / "goals-x"
    link.symlink_to(external, target_is_directory=True)

    # Without --force: blocked; the link and its target are untouched.
    report = install_bundled_skills(["claude"], bundled_dir=bundled, target_dirs=dirs)
    assert [r.status for r in report.results] == ["blocked"]
    assert link.is_symlink()
    assert "user." in (external / "SKILL.md").read_text()

    # With --force: the link is replaced by a real dir; the external target survives.
    forced = install_bundled_skills(["claude"], force=True, bundled_dir=bundled, target_dirs=dirs)
    assert [r.status for r in forced.results] == ["overwritten"]
    assert not link.is_symlink()
    assert "Bundled skill" in (link / "SKILL.md").read_text()
    assert "user." in (external / "SKILL.md").read_text()


def test_render_marks_uninstalled_bundled_and_truncates(tmp_path: Path) -> None:
    long_desc = "x" * 300
    out = render_skills_list(
        [
            DiscoveredSkill(
                name="goals-x", description=long_desc, sources=["bundled"], agents=[], path="/p"
            )
        ]
    )

    assert "not installed (bundled)" in out
    assert "…" in out and len(out) < 200
