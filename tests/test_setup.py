import json
from pathlib import Path

from goals.setup import setup_agents


def _claude_settings(home: Path) -> dict:
    return json.loads((home / "settings.json").read_text())


def test_claude_setup_registers_marketplace_and_enables_plugin(tmp_path: Path) -> None:
    claude = tmp_path / "claude"
    report = setup_agents(["claude"], claude_home=claude, codex_home=tmp_path / "codex")
    assert report.dry_run is False
    settings = _claude_settings(claude)
    assert settings["extraKnownMarketplaces"]["goals"]["source"]["repo"] == "ShivamGupta42/goals"
    assert settings["enabledPlugins"]["goals@goals"] is True
    # bundled skills landed in ~/.claude/skills
    assert (claude / "skills").is_dir()
    assert any(p.is_dir() for p in (claude / "skills").iterdir())


def test_claude_setup_preserves_existing_settings(tmp_path: Path) -> None:
    claude = tmp_path / "claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({"theme": "dark", "enabledPlugins": {"other@x": True}}))
    setup_agents(["claude"], claude_home=claude, codex_home=tmp_path / "codex")
    settings = _claude_settings(claude)
    assert settings["theme"] == "dark"  # untouched
    assert settings["enabledPlugins"]["other@x"] is True  # preserved
    assert settings["enabledPlugins"]["goals@goals"] is True  # added


def test_claude_setup_is_idempotent(tmp_path: Path) -> None:
    claude = tmp_path / "claude"
    setup_agents(["claude"], claude_home=claude, codex_home=tmp_path / "codex")
    report = setup_agents(["claude"], claude_home=claude, codex_home=tmp_path / "codex")
    # Second run reports no settings change.
    assert any("already configured" in a.detail for a in report.actions)
    assert not any(a.changed and "marketplace" in a.detail for a in report.actions)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    claude = tmp_path / "claude"
    report = setup_agents(["claude"], dry_run=True, claude_home=claude, codex_home=tmp_path / "codex")
    assert report.dry_run is True
    assert not (claude / "settings.json").exists()
    assert not (claude / "skills").exists()
    assert report.actions  # but it described what it would do


def test_codex_setup_installs_skills(tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    setup_agents(["codex"], claude_home=tmp_path / "claude", codex_home=codex)
    assert (codex / "skills").is_dir()
    assert any(p.is_dir() for p in (codex / "skills").iterdir())


def test_both_targets(tmp_path: Path) -> None:
    report = setup_agents(
        ["claude", "codex"], claude_home=tmp_path / "claude", codex_home=tmp_path / "codex"
    )
    targets = {a.target for a in report.actions}
    assert targets == {"claude", "codex"}
    assert (tmp_path / "claude" / "settings.json").exists()
    assert (tmp_path / "codex" / "skills").is_dir()
