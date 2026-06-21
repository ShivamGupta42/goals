from __future__ import annotations

import tempfile
from pathlib import Path

from goals.loop_builder import new_session, run_script, save_design
from goals.models import SimulationReport, SimulationScenarioResult
from goals.runtime import create_goal, load_active_snapshot
from goals.skill_capabilities import analyze_skill_capabilities
from goals.tools import analyze_tools


def run_simulations() -> SimulationReport:
    scenarios = [
        _simulate_cold_resume(),
        _simulate_loop_script_reset_shape(),
        _simulate_missing_skill(),
        _simulate_tool_fallback(),
    ]
    passed = all(scenario.passed for scenario in scenarios)
    return SimulationReport(
        passed=passed,
        summary=f"{sum(1 for scenario in scenarios if scenario.passed)}/{len(scenarios)} simulation(s) passed.",
        scenarios=scenarios,
    )


def render_simulation_report(report: SimulationReport) -> str:
    lines = [
        "# Goals Simulation Report",
        "",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        report.summary,
    ]
    for scenario in report.scenarios:
        lines.extend(["", f"## {scenario.name}", ""])
        lines.append(f"Status: {'pass' if scenario.passed else 'needs attention'}")
        lines.append(scenario.summary)
        if scenario.checks:
            lines.append("Checks:")
            lines.extend(f"- {check}" for check in scenario.checks)
        if scenario.friction:
            lines.append("Friction:")
            lines.extend(f"- {item}" for item in scenario.friction)
    return "\n".join(lines) + "\n"


def _simulate_cold_resume() -> SimulationScenarioResult:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        create_goal("simulate cold resume", repo, workspace="in_place")
        snapshot = load_active_snapshot(repo)
        state = repo / ".goals" / "goal-state.json"
        markdown = repo / ".goals" / "GOAL.md"
        passed = state.exists() and markdown.exists() and snapshot.current_phase == "P1"
        return SimulationScenarioResult(
            name="cold-resume-portable-state",
            passed=passed,
            summary="A new goal exported committed portable state immediately.",
            checks=[str(state), str(markdown)],
            friction=[] if passed else ["Portable state was missing after goal creation."],
        )


def _simulate_loop_script_reset_shape() -> SimulationScenarioResult:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / ".goals"
        session = new_session(out)
        script = [
            "objective Demo loop",
            "dod Done",
            "add Plan :: Decide shape",
            "accept Plan is clear",
            "terminate Plan accepted",
            "profile frontend-landing",
            "save",
        ]
        run_script(session, script, write=lambda _line: None)
        save_design(session.design, out, skills=session.skills, profile_root=Path(tmp))
        state = (out / "goal-state.json").read_text(encoding="utf-8")
        passed = "Terminate when:" not in state and "Use skill:" not in state and "protocol" in state
        return SimulationScenarioResult(
            name="loop-protocol-structure",
            passed=passed,
            summary="Loop export keeps protocol metadata out of acceptance criteria.",
            checks=[str(out / "goal-state.json")],
            friction=[] if passed else ["Loop metadata leaked into acceptance criteria."],
        )


def _simulate_missing_skill() -> SimulationScenarioResult:
    report = analyze_skill_capabilities("Build a frontend landing page with browser testing", skills=[])
    passed = not report.passed and any(finding.status == "unknown" for finding in report.findings)
    return SimulationScenarioResult(
        name="missing-skill-preflight",
        passed=passed,
        summary="A frontend/browser task with no skills surfaces missing capabilities.",
        checks=[report.summary],
        friction=[] if passed else ["Missing capabilities were not surfaced."],
    )


def _simulate_tool_fallback() -> SimulationScenarioResult:
    report = analyze_tools()
    passed = bool(report.checks)
    return SimulationScenarioResult(
        name="tool-health",
        passed=passed,
        summary="Tool health reports concrete adapter/browser status.",
        checks=[f"{check.tool}:{check.status}" for check in report.checks],
        friction=[] if passed else ["No tool checks were produced."],
    )
