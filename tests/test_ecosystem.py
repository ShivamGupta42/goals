from pathlib import Path

import pytest

from goals.ecosystem import recommend_ecosystem_tools, render_recommendations
from goals.models import GoalSnapshot, WorktreeLease
from goals.registry import validate_registry_file
from goals.runtime import default_phases
from goals.storage import GoalsError


def test_ecosystem_recommendations_match_goal_phase_and_project_signals(tmp_path: Path) -> None:
    registry_root = tmp_path / "registries"
    registry_root.mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "tests").mkdir()
    (registry_root / "skills.yml").write_text(
        """
version: 1
kind: skills
skills:
  decision-explainer:
    label: Decision Explainer
    description: Explain risky technical tradeoffs.
    use_when: [migration, risk, decision]
    phases: [P2]
    command_hint: goals decision explain --file decision.json --level basic
  testing:
    label: Testing
    description: Prove implementation with tests.
    use_when: [pytest, tests, proof]
    phases: [P3, P4]
"""
    )
    (registry_root / "plugins.yml").write_text(
        """
version: 1
kind: plugins
plugins:
  browser:
    label: Browser
    description: Inspect local dashboards.
    use_when: [dashboard, html, visual]
    phases: [P4]
"""
    )
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Explain migration risk and update tests",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Explain migration risk and update tests"),
        current_phase="P2",
    )

    recommendations = recommend_ecosystem_tools(tmp_path, snapshot, limit=2)
    rendered = render_recommendations(recommendations)

    assert recommendations[0].name == "decision-explainer"
    assert recommendations[0].kind == "skill"
    assert recommendations[0].source_registry == "skills.yml"
    assert "migration" in recommendations[0].reason
    assert "goals decision explain" in rendered


def test_registry_validation_rejects_unknown_skill_entry_field(tmp_path: Path) -> None:
    path = tmp_path / "skills.yml"
    path.write_text(
        """
version: 1
kind: skills
skills:
  bad:
    label: Bad
    shell: rm -rf .
"""
    )

    with pytest.raises(GoalsError):
        validate_registry_file(path)
