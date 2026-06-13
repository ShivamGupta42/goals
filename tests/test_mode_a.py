from pathlib import Path

from goals.mode_a import build_mode_a_plan
from goals.models import GoalSnapshot, WorktreeLease
from goals.runtime import default_phases


def snapshot_for(tmp_path: Path) -> GoalSnapshot:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[dependency-groups]\ndev = ['pytest', 'ruff']\n"
    )
    (tmp_path / "tests").mkdir()
    return GoalSnapshot(
        goal_id="demo",
        objective="Improve Mode A",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Improve Mode A"),
        current_phase="P1",
    )


def test_build_mode_a_plan_selects_ready_claude(monkeypatch, tmp_path: Path) -> None:
    def fake_adapter_check(name: str) -> tuple[bool, str]:
        return name == "claude", f"{name} detail"

    monkeypatch.setattr("goals.mode_a.adapter_check", fake_adapter_check)
    plan = build_mode_a_plan(snapshot_for(tmp_path), "auto")
    assert plan.adapter == "claude"
    assert plan.adapter_ready is True
    assert "Claude Mode A notes" in plan.prompt
    assert "goals phase evidence P1 --file" in plan.prompt
    assert "uv run pytest -q" in plan.recommended_checks
    assert "uv run goals safety-check --mode local ." in plan.recommended_checks


def test_build_mode_a_plan_can_target_codex_when_not_ready(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("goals.mode_a.adapter_check", lambda name: (False, "feature disabled"))
    plan = build_mode_a_plan(snapshot_for(tmp_path), "codex")
    assert plan.adapter == "codex"
    assert plan.adapter_ready is False
    assert "Codex Mode A notes" in plan.prompt
    assert "feature disabled" in plan.prompt
