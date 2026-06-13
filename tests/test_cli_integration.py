import json
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )


def run_unchecked(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )


def init_repo(path: Path) -> None:
    run(["git", "init"], path)
    run(["git", "config", "user.email", "test@example.com"], path)
    run(["git", "config", "user.name", "Test User"], path)
    (path / "README.md").write_text("# Demo\n")
    (path / "LICENSE").write_text("MIT\n")
    run(["git", "add", "README.md", "LICENSE"], path)
    run(["git", "commit", "-m", "init"], path)


def test_create_status_dashboard_validate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(
        [
            "python",
            "-m",
            "goals.cli",
            "create",
            "Add tags to tasks and update tests",
            "--why",
            "Make tasks easier to organize.",
            "--adapter",
            "claude",
        ],
        repo,
    )
    assert "Created goal" in result.stdout
    assert "Adapter: claude" in result.stdout
    assert "Claude Mode A notes" in result.stdout
    worktree_line = next(
        line for line in result.stdout.splitlines() if line.startswith("Worktree:")
    )
    worktree = Path(worktree_line.split(":", 1)[1].strip())
    goal_file = next((worktree / ".agent-workflow" / "goals").glob("*/goal.json"))
    assert json.loads(goal_file.read_text())["why"] == "Make tasks easier to organize."
    status = run(["python", "-m", "goals.cli", "status"], worktree)
    assert "Add tags" in status.stdout
    run_prompt = run(["python", "-m", "goals.cli", "run", "--adapter", "codex"], worktree)
    assert "Codex Mode A notes" in run_prompt.stdout
    dash = run(["python", "-m", "goals.cli", "dashboard"], worktree)
    assert Path(dash.stdout.strip()).exists()
    validate = run(["python", "-m", "goals.cli", "validate"], worktree)
    assert "Validated goal" in validate.stdout
    local_safety = run(
        ["python", "-m", "goals.cli", "safety-check", "--mode", "local", "."], worktree
    )
    assert "public_repo_hygiene: pass" in local_safety.stdout
    publish_safety = run_unchecked(
        ["python", "-m", "goals.cli", "safety-check", "--mode", "publish", "."], worktree
    )
    assert publish_safety.returncode == 1
    assert "public_repo_hygiene: fail" in publish_safety.stdout


def test_create_refuses_dirty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "dirty.txt").write_text("not committed\n")
    result = run_unchecked(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    assert result.returncode == 1
    assert "dirty working tree" in result.stdout


def test_create_refuses_branch_collision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    run(["git", "branch", "goal/ship-demo"], repo)
    result = run_unchecked(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    assert result.returncode == 1
    assert "Branch already exists" in result.stdout


def test_validate_detects_stale_snapshot_and_repair_restores_it(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    worktree = Path(
        next(line for line in result.stdout.splitlines() if line.startswith("Worktree:"))
        .split(":", 1)[1]
        .strip()
    )
    goal_file = next((worktree / ".agent-workflow" / "goals").glob("*/goal.json"))
    snapshot = json.loads(goal_file.read_text())
    snapshot["objective"] = "Tampered outside the event log"
    goal_file.write_text(json.dumps(snapshot))

    validate = run_unchecked(["python", "-m", "goals.cli", "validate"], worktree)
    assert validate.returncode == 1
    assert "does not match the event log" in validate.stdout

    repair = run(["python", "-m", "goals.cli", "repair"], worktree)
    assert "Repaired" in repair.stdout
    validate_after_repair = run(["python", "-m", "goals.cli", "validate"], worktree)
    assert "Validated goal" in validate_after_repair.stdout


def test_phase_protocol_accepts_reviewed_phase(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    worktree = Path(
        next(line for line in result.stdout.splitlines() if line.startswith("Worktree:"))
        .split(":", 1)[1]
        .strip()
    )
    evidence = json.dumps(
        {"checks_run": ["pytest"], "acceptance_met": ["done"], "confidence": 0.9, "notes": "done"}
    )
    evidence_file = worktree / "evidence.json"
    evidence_file.write_text(evidence)
    run(["python", "-m", "goals.cli", "phase", "start", "P1"], worktree)
    run(
        ["python", "-m", "goals.cli", "phase", "evidence", "P1", "--file", str(evidence_file)],
        worktree,
    )
    run(["python", "-m", "goals.cli", "phase", "review", "P1"], worktree)
    accept = run(["python", "-m", "goals.cli", "phase", "accept", "P1"], worktree)
    assert "Accepted phase P1" in accept.stdout
