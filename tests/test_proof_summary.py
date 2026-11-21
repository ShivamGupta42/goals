"""The one-line 'Checks:' summary of how a goal's proof was made."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from goals.brief import build_goal_brief, render_goal_brief
from goals.dashboard import render_dashboard
from goals.metrics import PROOF_LABELS as METRICS_LABELS
from goals.models import (
    Evidence,
    GoalSnapshot,
    Phase,
    PhaseStatus,
    Verification,
    WorktreeLease,
)
from goals.proof_summary import PROOF_LABELS, render_proof_line, summarize_proof
from goals.workflows import render_check_workflow, render_finish_workflow

SRC = Path(__file__).resolve().parents[1] / "src" / "goals"


def _snapshot(tmp_path: Path, *phases: Phase) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Ship the thing",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=list(phases),
        current_phase=phases[0].phase_id if phases else None,
    )


def _phase(phase_id: str, *verifications: Verification) -> Phase:
    return Phase(
        phase_id=phase_id,
        title=f"Phase {phase_id}",
        goal="Do it.",
        status=PhaseStatus.IN_PROGRESS,
        evidence=Evidence(verifications=list(verifications)) if verifications else None,
    )


def _auto(ran: bool = True, passed: bool = True, covers: str = "P1.C1") -> Verification:
    return Verification(covers=covers, kind="auto", command="true", ran=ran, passed=passed)


def _other(kind: str, covers: str) -> Verification:
    return Verification(covers=covers, kind=kind, rationale="why this cannot run locally")


def test_mixed_kinds_are_counted_and_named(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        _phase("P1", _auto(), _auto(covers="P1.C2")),
        _phase("P4", _auto(covers="P4.C1"), _other("manual", "P4.C3")),
    )
    assert render_proof_line(snap) == "Checks: 3 run by the engine, 1 by hand (P4.C3), 0 waived"


def test_zero_engine_and_waived_are_shown_so_a_gap_is_visible(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1", _other("manual", "P1.C1")))
    assert render_proof_line(snap) == "Checks: 0 run by the engine, 1 by hand (P1.C1), 0 waived"


def test_waived_and_production_are_listed_with_their_ids(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        _phase("P1", _auto(), _other("waived", "P1.C2"), _other("production", "P1.C3")),
    )
    line = render_proof_line(snap)
    assert "1 waived (P1.C2)" in line
    assert "1 checked in production (P1.C3)" in line


def test_auto_checks_the_engine_never_ran_are_not_counted_as_run(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1", _auto(ran=False, passed=False)))
    line = render_proof_line(snap)
    assert line.startswith("Checks: 0 run by the engine")
    assert "1 declared but not run" in line


def test_a_failed_engine_check_is_called_out(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1", _auto(), _auto(passed=False, covers="P1.C2")))
    summary = summarize_proof(snap)
    assert summary.engine == 2 and summary.engine_failed == 1
    assert "2 run by the engine (1 failed)" in render_proof_line(snap)


def test_a_goal_with_no_checks_says_so_and_does_not_crash(tmp_path: Path) -> None:
    assert render_proof_line(_snapshot(tmp_path, _phase("P1"))) == "Checks: none recorded yet"
    assert render_proof_line(_snapshot(tmp_path)) == "Checks: none recorded yet"


def test_long_id_lists_are_cut(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1", *[_other("manual", f"P1.C{i}") for i in range(1, 6)]))
    line = render_proof_line(snap)
    assert "5 by hand (P1.C1, P1.C2, P1.C3 +2 more)" in line


def test_a_long_covers_text_is_cut(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1", _other("manual", "x" * 200)))
    assert len(render_proof_line(snap)) < 120


def test_an_agent_written_id_cannot_imitate_the_line(tmp_path: Path) -> None:
    empty = render_proof_line(_snapshot(tmp_path, _phase("P1", _other("manual", "   "))))
    assert "1 by hand (unnamed)" in empty and "()" not in empty
    sneaky = render_proof_line(
        _snapshot(tmp_path, _phase("P1", _other("manual", "a, b) 0 waived")))
    )
    # Brackets and commas inside an id are dropped, so the counts stay the only structure.
    assert sneaky == "Checks: 0 run by the engine, 1 by hand (a b 0 waived), 0 waived"


def test_wording_is_shared_with_goals_metrics() -> None:
    """One source for the labels, so the two reports cannot drift apart."""
    assert METRICS_LABELS is PROOF_LABELS


def test_new_summary_never_names_the_cross_goal_report() -> None:
    """The agent reads this line, so it must not pull in the cross-goal numbers."""
    text = (SRC / "proof_summary.py").read_text()
    assert "goals.metrics" not in text and "import metrics" not in text
    tree = ast.parse(text)
    imported = {
        n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module is not None
    }
    assert "goals.metrics" not in imported


# --- the four places it shows ------------------------------------------- #
def test_brief_carries_and_prints_the_line(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1", _auto(), _other("manual", "P1.C2")))
    brief = build_goal_brief(snap)
    assert brief.proof_mix == "Checks: 1 run by the engine, 1 by hand (P1.C2), 0 waived"
    text = render_goal_brief(brief)
    assert brief.proof_mix in text
    # A brief made without the field (JSON without the key) loads with an empty default.
    data = json.loads(brief.model_dump_json())
    data.pop("proof_mix")
    assert type(brief).model_validate(data).proof_mix == ""


def test_a_brief_without_the_field_renders_without_the_line(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1"))
    brief = build_goal_brief(snap).model_copy(update={"proof_mix": ""})
    assert "Checks:" not in render_goal_brief(brief)


def _dashboard(snapshot: GoalSnapshot, tmp_path: Path) -> str:
    out = tmp_path / "dashboard.html"
    render_dashboard(snapshot, out)
    return out.read_text()


def test_dashboard_shows_the_line(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, _phase("P1", _auto(), _other("manual", "P1.C2")))
    html = _dashboard(snap, tmp_path)
    line = "Checks: 1 run by the engine, 1 by hand (P1.C2), 0 waived"
    assert html.count(line) == 1
    # It sits inside the 'Proof & evidence' section, before the next section starts.
    start = html.index("Proof &amp; evidence")
    assert start < html.index(line) < html.index("</details>", start)


def test_dashboard_with_no_checks_does_not_crash(tmp_path: Path) -> None:
    assert "Checks: none recorded yet" in _dashboard(_snapshot(tmp_path, _phase("P1")), tmp_path)


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", "-b", "feature"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(cmd, cwd=repo, check=True)
    (repo / "README.md").write_text("# demo\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def test_check_and_finish_print_real_counts(tmp_path: Path) -> None:
    from goals.models import Event, EventType
    from goals.runtime import append_event, create_goal, verify_phase
    from goals.workflows import check_workflow, finish_workflow

    repo = _git_repo(tmp_path)
    goal_id = create_goal("ship it", repo, workspace="in_place").goal_id
    checks = [
        Verification(covers="P1.C1", kind="auto", command="true"),
        Verification(covers="P1.C2", kind="manual", rationale="looked at it"),
    ]
    append_event(
        repo,
        Event(
            goal_id=goal_id,
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P1", "evidence": Evidence(verifications=checks).model_dump()},
        ),
    )
    verify_phase(repo, "P1")
    line = "- Checks: 1 run by the engine, 1 by hand (P1.C2), 0 waived"
    assert line in render_check_workflow(check_workflow(repo))
    assert line in render_finish_workflow(finish_workflow(repo))


def test_check_and_finish_print_the_line(tmp_path: Path) -> None:
    from goals.runtime import create_goal
    from goals.workflows import check_workflow, finish_workflow

    repo = _git_repo(tmp_path)
    create_goal("ship it", repo, workspace="in_place")
    check_text = render_check_workflow(check_workflow(repo))
    assert "Checks: none recorded yet" in check_text
    # The old 'Proof:' line stays, so nothing that read it breaks.
    assert "- Proof:" in check_text
    finish_text = render_finish_workflow(finish_workflow(repo))
    assert "- Checks: none recorded yet" in finish_text


# --- the assumption: counting from saved state agrees with the log ------- #
def test_counts_from_saved_state_match_the_cross_goal_report(tmp_path: Path) -> None:
    """A-5b47faa0: the per-goal line and the log-based report must tell the same story."""
    from goals.metrics import summarize_log
    from goals.models import Event, EventType
    from goals.runtime import append_event, create_goal, load_active_snapshot, verify_phase

    repo = _git_repo(tmp_path)
    snap = create_goal("ship it", repo, workspace="in_place")
    goal_id = snap.goal_id
    log = repo / ".agent-workflow" / "goals" / goal_id / "events.jsonl"
    checks = [
        Verification(covers="P1.C1", kind="auto", command="true"),
        Verification(covers="P1.C2", kind="auto", command="exit 1"),
        Verification(covers="P1.C3", kind="manual", rationale="looked at it"),
        Verification(covers="P1.C4", kind="waived", rationale="cannot run here"),
        Verification(covers="P1.C5", kind="production", rationale="checked live"),
    ]
    append_event(
        repo,
        Event(
            goal_id=goal_id,
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P1", "evidence": Evidence(verifications=checks).model_dump()},
        ),
    )

    def kinds_from_state() -> dict[str, int]:
        s = summarize_proof(load_active_snapshot(repo))
        return {
            k: v
            for k, v in {
                "auto": s.engine,
                "not_run": s.not_run,
                "manual": len(s.by_hand),
                "waived": len(s.waived),
                "production": len(s.production),
            }.items()
            if v
        }

    # Before verify: both auto checks are only declared.
    assert kinds_from_state() == summarize_log(log).proof_kinds
    assert kinds_from_state()["not_run"] == 2

    # After verify: the engine ran both (one failed); the two reports still agree.
    verify_phase(repo, "P1")
    assert kinds_from_state() == summarize_log(log).proof_kinds
    after = summarize_proof(load_active_snapshot(repo))
    assert (after.engine, after.engine_failed, after.not_run) == (2, 1, 0)


def test_a_finished_goal_with_no_evidence_still_prints_the_line(tmp_path: Path) -> None:
    from goals.models import GoalStatus

    snap = _snapshot(tmp_path, _phase("P1")).model_copy(update={"status": GoalStatus.COMPLETE})
    assert "Checks: none recorded yet" in render_goal_brief(build_goal_brief(snap))


def test_nothing_that_decides_pass_or_fail_reads_the_line() -> None:
    """Display only: the line may be read only inside functions that build or print it.

    Checking the module name alone would miss a gate that reads `brief.proof_mix`, or a
    gate inside workflows.py, so look at which function each use sits in.
    """
    names = {"render_proof_line", "summarize_proof", "proof_mix", "ProofSummary"}
    allowed = {
        "build_goal_brief",  # fills the field
        "render_goal_brief",
        "render_check_workflow",
        "render_finish_workflow",
        "_evidence_detail_html",  # the dashboard paragraph
    }
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "proof_summary.py":
            continue
        tree = ast.parse(path.read_text())
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef) or func.name in allowed:
                continue
            for node in ast.walk(func):
                used = (isinstance(node, ast.Name) and node.id in names) or (
                    isinstance(node, ast.Attribute) and node.attr in names
                )
                if used:
                    offenders.append(f"{path.name}:{func.name}")
    assert offenders == []
    # And no module that decides anything imports it (metrics only shares the labels).
    users = sorted(
        p.name
        for p in SRC.rglob("*.py")
        if p.name != "proof_summary.py" and "proof_summary" in p.read_text()
    )
    assert users == ["brief.py", "dashboard.py", "metrics.py", "workflows.py"]
