import json
from pathlib import Path

from typer.testing import CliRunner

from goals.brief import build_goal_brief
from goals.capabilities import analyze_capabilities, render_capability_report
from goals.cli import app
from goals.dashboard import render_dashboard
from goals.issues import analyze_goal_issues
from goals.models import (
    CapabilityCheckReport,
    CapabilityGap,
    GoalSnapshot,
    Phase,
    WorktreeLease,
)
from goals.runtime import create_goal
from goals.skill_discovery import DiscoveredSkill

runner = CliRunner()


def _snapshot(tmp_path: Path, *, objective: str = "Build a CLI") -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective=objective,
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Build",
                goal=objective,
                acceptance_criteria=["Done"],
            )
        ],
        current_phase="P1",
    )


def _skill(name: str, *, sources: list[str], agents: list[str]) -> DiscoveredSkill:
    return DiscoveredSkill(
        name=name,
        description=f"{name} skill.",
        sources=sources,
        agents=agents,
        path=f"/skills/{name}/SKILL.md",
    )


def test_missing_browser_need_is_first_class_gap(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, objective="Build a website and verify it with screenshots")

    report = analyze_capabilities(snapshot, skills=[])
    rendered = render_capability_report(report)

    assert report.passed is False
    assert report.gaps[0].category == "browser"
    assert report.gaps[0].status == "missing"
    assert report.gaps[0].needs_user is True
    assert "Browser/UI verification" in rendered


def test_browser_need_with_unrelated_skill_does_not_crash(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, objective="Build a website and verify it with screenshots")

    report = analyze_capabilities(
        snapshot,
        skills=[_skill("spreadsheet-helper", sources=["codex"], agents=["codex"])],
    )

    assert report.passed is False
    assert any(gap.category == "browser" for gap in report.gaps)


def test_claude_only_skill_is_missing_for_codex(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)

    report = analyze_capabilities(
        snapshot,
        adapter="codex",
        explicit_needs=["skill:research-helper"],
        skills=[_skill("research-helper", sources=["claude"], agents=["claude"])],
    )

    assert report.passed is False
    assert report.gaps[0].status == "missing_for_agent"
    assert report.gaps[0].needs_user is True
    assert "claude" in report.gaps[0].detail


def test_bundled_skill_gap_suggests_install(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)

    report = analyze_capabilities(
        snapshot,
        adapter="codex",
        explicit_needs=["skill:goals-architecture-map"],
        skills=[_skill("goals-architecture-map", sources=["bundled"], agents=[])],
    )

    assert report.passed is False
    assert report.gaps[0].status == "needs_install"
    assert report.gaps[0].needs_user is False
    assert "goals skills install --target codex" in report.gaps[0].suggested_action


def test_available_skill_satisfies_need(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)

    report = analyze_capabilities(
        snapshot,
        adapter="codex",
        explicit_needs=["skill:goals-problem-solving"],
        skills=[_skill("goals-problem-solving", sources=["codex"], agents=["codex"])],
    )

    assert report.passed is True
    assert report.gaps == []


def test_capability_gaps_surface_in_issues_and_brief(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("goals.capabilities.discover_skills", lambda: [])
    snapshot = _snapshot(tmp_path, objective="Build a visual browser dashboard")

    issues = analyze_goal_issues(snapshot)
    brief = build_goal_brief(snapshot)

    assert any(issue.area == "capability" for issue in issues.issues)
    assert issues.user_questions
    assert brief.waiting_on == "you"
    assert any(action.source == "capability" for action in brief.user_actions)


def test_dashboard_capability_section_is_hidden_when_clean(tmp_path: Path, monkeypatch) -> None:
    clean_report = CapabilityCheckReport(
        goal_id="demo",
        adapter="auto",
        passed=True,
        summary="No capability needs detected.",
    )
    monkeypatch.setattr("goals.dashboard.analyze_capabilities", lambda snapshot: clean_report)
    output = tmp_path / "dashboard.html"

    render_dashboard(_snapshot(tmp_path), output)

    assert "Capabilities" not in output.read_text(encoding="utf-8")


def test_dashboard_capability_section_renders_gaps(tmp_path: Path, monkeypatch) -> None:
    report = CapabilityCheckReport(
        goal_id="demo",
        adapter="auto",
        passed=False,
        summary="Found 1 capability gap.",
        gaps=[
            CapabilityGap(
                need_id="browser",
                title="Browser/UI verification",
                category="browser",
                status="missing",
                needs_user=True,
                detail="No browser skill is installed.",
                suggested_action="Ask the user to approve a browser skill.",
            )
        ],
    )
    monkeypatch.setattr("goals.dashboard.analyze_capabilities", lambda snapshot: report)
    monkeypatch.setattr("goals.issues.analyze_capabilities", lambda snapshot: report)
    output = tmp_path / "dashboard.html"

    render_dashboard(_snapshot(tmp_path, objective="Build a browser UI"), output)

    html = output.read_text(encoding="utf-8")
    assert "Capabilities" in html
    assert "Browser/UI verification" in html


def test_capability_cli_json_parses(tmp_path: Path, monkeypatch) -> None:
    create_goal("Ship capability json", tmp_path, workspace="in_place")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "capability",
            "check",
            "--need",
            "skill:no-such-skill-for-capability-test-xyz",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["passed"] is False
    assert data["gaps"][0]["status"] == "missing"
