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
    assert "goals issues" in plan.prompt
    assert "goals brief" in plan.prompt
    assert plan.architecture_file.endswith("architecture.md")
    assert "Architecture map:" in plan.prompt
    assert "goals architecture check" in plan.prompt
    assert "Parallel worktree merge gate:" in plan.prompt
    assert plan.recommended_tools
    assert "Recommended skills/plugins for this phase:" in plan.prompt
    assert "goals ecosystem discover" in plan.prompt
    assert "skills/plugins/adapters" in plan.prompt
    assert "goals ecosystem sync" in plan.prompt
    assert "goals ecosystem merge" in plan.prompt
    assert "Permission policy:" in plan.prompt
    assert "goals permission check" in plan.prompt
    assert "Professional boundaries:" in plan.prompt
    assert "goals boundary explain --domain auto" in plan.prompt
    assert "External review gate:" in plan.prompt
    assert "goals external-review add" in plan.prompt
    assert "goals external-review check" in plan.prompt
    assert "Self-evolution memory:" in plan.prompt
    assert "goals memory sync" in plan.prompt
    assert "goals roadmap suggest" in plan.prompt
    assert "goals memory record" in plan.prompt
    assert "Source evidence:" in plan.prompt
    assert "goals source add" in plan.prompt
    assert "Citation quality:" in plan.prompt
    assert "goals source citations" in plan.prompt
    assert "goals source freshness" in plan.prompt
    assert "Asset provenance:" in plan.prompt
    assert "goals asset add" in plan.prompt
    assert "goals asset provenance" in plan.prompt
    assert "Creative variants:" in plan.prompt
    assert "goals creative variant add" in plan.prompt
    assert "goals creative compare" in plan.prompt
    assert "Handoff owners:" in plan.prompt
    assert "goals handoff owner add" in plan.prompt
    assert "goals handoff check" in plan.prompt
    assert "uv run goals asset provenance --strict" in plan.recommended_checks
    assert "uv run goals creative compare --strict" in plan.recommended_checks
    assert "uv run goals handoff check --strict" in plan.recommended_checks
    assert "uv run goals external-review check --strict" in plan.recommended_checks
    assert "uv run goals architecture check --strict" in plan.recommended_checks
    assert "uv run goals source citations --strict" in plan.recommended_checks
    assert "uv run goals source freshness --strict" in plan.recommended_checks
    assert "uv run goals boundary explain --domain auto" in plan.recommended_checks
    assert "uv run pytest -q" in plan.recommended_checks
    assert "uv run goals brief" in plan.recommended_checks
    assert "source_ids" in plan.evidence_template.model_dump()
    assert "uv run goals safety-check --mode local ." in plan.recommended_checks


def test_build_mode_a_plan_can_target_codex_when_not_ready(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("goals.mode_a.adapter_check", lambda name: (False, "feature disabled"))
    plan = build_mode_a_plan(snapshot_for(tmp_path), "codex")
    assert plan.adapter == "codex"
    assert plan.adapter_ready is False
    assert "Codex Mode A notes" in plan.prompt
    assert "feature disabled" in plan.prompt
