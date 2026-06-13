from pathlib import Path

import pytest

from goals.dashboard import render_dashboard
from goals.models import (
    Decision,
    DecisionOption,
    Evidence,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    Phase,
    PhaseStatus,
    WorktreeLease,
)
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


def test_publish_safety_blocks_self_evolution_memory(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("MIT\n")
    memory_dir = tmp_path / ".agent-workflow" / "self-evolution"
    memory_dir.mkdir(parents=True)
    (memory_dir / "memory.json").write_text('{"entries":[]}\n')

    results = {result.scanner: result for result in run_safety_scanners(tmp_path)}

    assert results["public_repo_hygiene"].findings


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
    assert "Goal Brief" in text
    assert "What Needs Your Answer" in text
    assert "What the Agent Can Do Next" in text
    assert "Progress" in text
    assert "Issues" in text
    assert "Decisions Needed" in text
    assert "Suggested Skills and Plugins" in text
    assert "Self-Evolution Memory" in text
    assert "Architecture Map" in text
    assert "Architecture Brief" in text
    assert "Review focus" in text
    assert "Evidence gaps and open questions" in text
    assert "Sources" in text
    assert "No decisions are waiting on you." in text
    assert "P1 has no evidence yet." in text
    assert "Goal ID:" in text
    assert "Event offset:" in text
    assert "Source commit:" in text


def test_dashboard_explains_only_important_decisions(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add tags to tasks",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Inspect storage",
                goal="Find the storage shape",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    changed_files=["src/db.py"],
                    checks_run=["pytest"],
                    known_gaps=["Migration order is unclear."],
                    acceptance_met=["Storage inspected."],
                    confidence=0.8,
                    notes="Storage is file-backed today.",
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.PASS,
                        summary="ok",
                    )
                ],
            )
        ],
        current_phase="P1",
        decisions=[
            Decision(
                title="Choose tag storage",
                plain_summary="Pick where task tags should live.",
                why_it_matters="This affects migration risk.",
                recommendation="Store tags in the existing task file",
                options=[
                    DecisionOption(
                        label="Existing file",
                        explanation="No migration needed.",
                        tradeoffs=["Less scalable."],
                        reversible=True,
                        reversal_plan="Move tags later with a storage adapter.",
                        risk="low",
                    ),
                    DecisionOption(
                        label="New migration",
                        explanation="<script>structured storage</script>",
                        tradeoffs=["Migration ordering risk."],
                        reversible=False,
                        risk="high",
                    ),
                ],
                confidence=0.74,
                priority="blocking",
                suggested_reply="Use the existing task file.",
                technical_details="Migration order has to be coordinated.",
            ),
            Decision(
                title="Dashboard label wording",
                plain_summary="Choose label wording for the dashboard.",
                why_it_matters="It affects presentation only.",
                recommendation="Use the shorter label.",
                options=[
                    DecisionOption(
                        label="Short label",
                        explanation="Easy to scan.",
                        reversible=True,
                        risk="low",
                    )
                ],
                confidence=0.9,
                priority="later",
            ),
        ],
    )
    output = tmp_path / "dashboard.html"

    render_dashboard(snapshot, output)
    text = output.read_text()

    assert "Choose tag storage" in text
    assert "Decision Brief" in text
    assert "What Needs Your Answer" in text
    assert "What the Agent Can Handle" in text
    assert "What happens next" in text
    assert "1 routine/reversible choice(s) can stay with the agent." in text
    assert "Why this needs you" in text
    assert "Recommended option" in text
    assert "Store tags in the existing task file" in text
    assert "Risk: low" in text
    assert "Risk: high" in text
    assert "Reversible: yes" in text
    assert "Reversible: not clearly" in text
    assert "Changed files: src/db.py" in text
    assert "Checks run: pytest" in text
    assert "Migration order is unclear." in text
    assert "Migration order has to be coordinated." in text
    assert "Use the existing task file." in text
    assert "<script>structured storage</script>" not in text
    assert "&lt;script&gt;structured storage&lt;/script&gt;" in text
    assert "Choose label wording for the dashboard." not in text
    assert "Dashboard label wording" not in text
