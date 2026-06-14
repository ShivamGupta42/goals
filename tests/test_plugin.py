import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from goals.agent_hooks import session_start_payload, stop_payload
from goals.cli import app
from goals.runtime import create_goal

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _repo_with_goal(path: Path) -> None:
    _run(["git", "init", "-b", "feature"], path)
    _run(["git", "config", "user.email", "t@e.com"], path)
    _run(["git", "config", "user.name", "T"], path)
    _run(["git", "commit", "--allow-empty", "-m", "init"], path)
    create_goal("ship the plugin", path, workspace="in_place")


# --- hook backends --------------------------------------------------------- #
def test_session_start_injects_active_goal(tmp_path: Path) -> None:
    _repo_with_goal(tmp_path)
    payload = json.loads(session_start_payload(tmp_path))
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "ship the plugin" in payload["hookSpecificOutput"]["additionalContext"]


def test_session_start_is_silent_without_a_goal(tmp_path: Path) -> None:
    _run(["git", "init", "-b", "feature"], tmp_path)
    assert session_start_payload(tmp_path) == ""


def test_stop_is_a_noop_unless_enforced(tmp_path: Path) -> None:
    _repo_with_goal(tmp_path)
    assert stop_payload(tmp_path, enforce=False) == ""


def test_stop_blocks_when_enforced_and_work_remains(tmp_path: Path) -> None:
    _repo_with_goal(tmp_path)  # fresh goal: waiting on the agent
    payload = json.loads(stop_payload(tmp_path, enforce=True))
    assert payload["decision"] == "block"
    assert "ship the plugin" in payload["reason"]


def test_stop_is_silent_without_a_goal(tmp_path: Path) -> None:
    _run(["git", "init", "-b", "feature"], tmp_path)
    assert stop_payload(tmp_path, enforce=True) == ""


# --- hooks CLI ------------------------------------------------------------- #
def test_hooks_session_start_command(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["hooks", "session-start"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_hooks_session_start_empty_without_goal(tmp_path: Path, monkeypatch) -> None:
    _run(["git", "init", "-b", "feature"], tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["hooks", "session-start"])
    assert result.exit_code == 0
    assert result.stdout == ""


# --- plugin manifests ------------------------------------------------------ #
def test_plugin_manifest_is_valid() -> None:
    data = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert data["name"] == "goals"
    assert data["version"] and data["description"]


def test_marketplace_manifest_lists_the_plugin() -> None:
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert data["name"] == "goals"
    names = [p["name"] for p in data["plugins"]]
    assert "goals" in names


def test_hooks_json_wires_session_start_and_stop() -> None:
    data = json.loads((REPO / "hooks" / "hooks.json").read_text())
    events = data["hooks"]
    assert "SessionStart" in events and "Stop" in events
    cmds = [
        h["command"]
        for group in events.values()
        for entry in group
        for h in entry["hooks"]
    ]
    assert "goals hooks session-start" in cmds
    assert "goals hooks stop" in cmds


def test_commands_exist_with_frontmatter() -> None:
    for name in ("create", "next", "check", "diagram", "improve"):
        text = (REPO / "commands" / f"{name}.md").read_text()
        assert text.startswith("---")  # frontmatter
        assert "description:" in text
