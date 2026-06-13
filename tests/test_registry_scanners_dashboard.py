from pathlib import Path

import pytest

from goals.dashboard import render_dashboard
from goals.models import GoalSnapshot, WorktreeLease
from goals.registry import validate_registry_file
from goals.runtime import default_phases
from goals.scanners import run_safety_scanners
from goals.storage import GoalsError


def test_registry_rejects_unknown_critical_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text("version: 1\nkind: gates\nsurprise: true\n")
    with pytest.raises(GoalsError):
        validate_registry_file(path)


def test_safety_scanner_detects_secret_and_local_path(tmp_path: Path) -> None:
    secret_label = "api" + "_key"
    local_path = "/" + "Users/example/private"
    (tmp_path / "README.md").write_text(
        f"{secret_label} = 'abcdefghijklmnopqrstuvwxyz'\n{local_path}\n"
    )
    (tmp_path / "LICENSE").write_text("MIT\n")
    results = {result.scanner: result for result in run_safety_scanners(tmp_path)}
    assert results["secrets"].findings
    assert results["local_paths"].findings


def test_dashboard_escapes_html(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="<script>alert(1)</script>",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
    assert "Progress" in text
    assert "Decisions Needed" in text
    assert "Architecture Map" in text
    assert "No decisions are waiting on you." in text
    assert "Goal ID:" in text
    assert "Event offset:" in text
    assert "Source commit:" in text
