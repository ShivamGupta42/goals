from pathlib import Path

from goals.mode_a import build_mode_a_plan
from goals.models import GoalSnapshot, WorktreeLease
from goals.runtime import default_phases
from goals.user_memory import add_preference


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
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    add_preference("communication", "Prefer concise explanations.")

    def fake_adapter_check(name: str) -> tuple[bool, str]:
        return name == "claude", f"{name} detail"

    monkeypatch.setattr("goals.mode_a.adapter_check", fake_adapter_check)
    plan = build_mode_a_plan(snapshot_for(tmp_path), "auto")
    assert plan.adapter == "claude"
    assert plan.adapter_ready is True
    assert "Claude Mode A notes" in plan.prompt
    assert "goals phase evidence P1 --file" in plan.prompt
    # The PACERS Assess step is wired into the CLI handoff, not just the Claude
    # skill, so a CLI-driven agent also populates the building journey.
    assert "goals assess assume" in plan.prompt
    assert "goals assess breakdown" in plan.prompt
    assert "goals issues" in plan.prompt
    assert "goals brief" in plan.prompt
    assert "Waiting on: you" in plan.prompt
    assert "ask exactly one plain-language question" in plan.prompt
    assert "Do not run review or accept until the user answers" in plan.prompt
    assert "goals checkpoint current" in plan.prompt
    assert plan.architecture_file.endswith("architecture.md")
    assert "Architecture map:" in plan.prompt
    assert "goals architecture check" in plan.prompt
    assert "Parallel worktree merge gate:" in plan.prompt
    assert "goals skills list" in plan.prompt
    assert "Permission policy:" in plan.prompt
    assert "goals permission check" in plan.prompt
    assert "Self-evolution memory:" in plan.prompt
    assert "goals memory sync" in plan.prompt
    assert "goals memory record" in plan.prompt
    assert "User personalization:" in plan.prompt
    assert "Prefer concise explanations" in plan.prompt
    assert "/insights" in plan.prompt
    assert "goals user import-insights --file -" in plan.prompt
    assert "Source evidence:" in plan.prompt
    assert "goals source add" in plan.prompt
    assert "goals source freshness" in plan.prompt
    assert "goals architecture check --strict" in plan.recommended_checks
    assert "goals source freshness --strict" in plan.recommended_checks
    assert "uv run pytest -q" in plan.recommended_checks
    assert "goals brief" in plan.recommended_checks
    assert "goals checkpoint current" in plan.recommended_checks
    assert "source_ids" in plan.evidence_template.model_dump()


def test_build_mode_a_plan_can_target_codex_when_not_ready(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("goals.mode_a.adapter_check", lambda name: (False, "feature disabled"))
    plan = build_mode_a_plan(snapshot_for(tmp_path), "codex")
    assert plan.adapter == "codex"
    assert plan.adapter_ready is False
    assert "Codex Mode A notes" in plan.prompt
    assert "goals user show" in plan.prompt
    assert "do not assume a native Codex `/insights` command exists" in plan.prompt
    assert "feature disabled" in plan.prompt


def test_short_handoff_is_calm_and_points_to_full(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("goals.mode_a.adapter_check", lambda name: (name == "claude", "ok"))
    snap = snapshot_for(tmp_path)
    short = build_mode_a_plan(snap, "claude", full=False).prompt
    full = build_mode_a_plan(snap, "claude", full=True).prompt
    # Short is genuinely shorter and still actionable.
    assert len(short) < len(full) / 2
    assert "Current phase: P1" in short
    assert "goals assess assume" in short  # PACERS Assess still front-and-center
    assert "goals phase evidence P1" in short
    assert "goals next --full" in short  # escape hatch to the complete protocol
    # The heavy gates live only in --full, not the default handoff.
    assert "Parallel worktree merge gate" not in short
    assert "Permission policy:" not in short
    assert "Self-evolution memory:" not in short
    assert "Parallel worktree merge gate" in full
    assert "Permission policy:" in full
    # Paths in the short handoff are relative to the worktree, not absolute.
    assert str(tmp_path) not in short.split("relative to the goal worktree")[0]
    assert ".agent-workflow/goals/demo/evidence-p1.json" in short
