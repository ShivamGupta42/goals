import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from goals.cli import app

runner = CliRunner()


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _repo_with_goal(path: Path) -> None:
    _run(["git", "init", "-b", "feature"], path)
    _run(["git", "config", "user.email", "t@example.com"], path)
    _run(["git", "config", "user.name", "T"], path)
    (path / "README.md").write_text("# demo\n")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", "init"], path)
    # In-place goal on a feature branch so state lives in this repo (no cd).
    from goals.runtime import create_goal

    create_goal("ship the json", path, workspace="in_place")


def test_status_json_parses(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["objective"] == "ship the json"
    assert data["current_phase"] == "P1"


def test_check_json_parses(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "passed" in data
    assert data["brief"]["goal_id"]
    assert "issues" in data


def test_context_json_has_active_goal_block(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["context", "show", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["objective"] == "ship the json"
    assert data["current_phase"] == "P1"
    assert data["acceptance_criteria"]  # P1 has acceptance criteria
    assert data["waiting_on"] in ("you", "agent", "no one")
    assert tmp_path.name in data["worktree_path"]


def test_context_text_block_renders(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["context", "show"])
    assert result.exit_code == 0
    assert "Active Goal" in result.stdout
    assert "ship the json" in result.stdout


def test_context_errors_cleanly_with_no_goal(tmp_path: Path, monkeypatch) -> None:
    _run(["git", "init", "-b", "feature"], tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["context", "show"])
    assert result.exit_code == 1
    assert "No active goal" in result.stdout
