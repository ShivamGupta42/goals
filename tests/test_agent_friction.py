"""Tests for the agent-experience friction fixes E1-E5.

Each fix moves a contract from "learned by failing" to "knowable before authoring".
See docs/AGENT_FRICTION_FIX_PLAN.md.
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from goals.cli import _load_json_model, app
from goals.gates import review_phase
from goals.models import (
    Evidence,
    GateFactType,
    GoalSnapshot,
    Phase,
    Verification,
    WorktreeLease,
)
from goals.phase_workflows import COMPLETION_CRITIQUE_NUDGE, PhaseAcceptReport
from goals.storage import GoalsError

runner = CliRunner()


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _repo_with_goal(path: Path) -> None:
    _run(["git", "init", "-b", "feature"], path)
    _run(["git", "config", "user.email", "t@example.com"], path)
    _run(["git", "config", "user.name", "T"], path)
    (path / "README.md").write_text("# demo\n")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", "init"], path)
    from goals.runtime import create_goal

    create_goal("ship the fix", path, workspace="in_place")


# --- E1b: friendly validation error names the bad key + allowed fields ------ #
def test_unknown_evidence_field_is_named_with_allowed_fields() -> None:
    bad = json.dumps({"summary": "nope", "verifications": []})
    with pytest.raises(GoalsError) as exc:
        _load_json_model(bad, None, Evidence)
    message = str(exc.value)
    assert "summary" in message  # names the offending key
    assert "Allowed top-level fields" in message
    assert "verifications" in message  # lists a real field
    assert "validation error" not in message.lower()  # not a raw pydantic dump


def test_valid_evidence_still_loads() -> None:
    ok = json.dumps({"confidence": 0.5, "notes": "fine"})
    model = _load_json_model(ok, None, Evidence)
    assert model.confidence == 0.5


def test_nested_unknown_field_is_reported_with_full_path() -> None:
    # A stray key inside verifications[0] must name the full path, not just the leaf.
    bad = json.dumps(
        {"verifications": [{"covers": "P1.C1", "kind": "auto", "command": "true", "bogus": 1}]}
    )
    with pytest.raises(GoalsError) as exc:
        _load_json_model(bad, None, Evidence)
    assert "verifications.0.bogus" in str(exc.value)


def test_mixed_extra_and_type_errors_are_both_surfaced() -> None:
    # An extra key AND a bad-type value: neither may be silently dropped.
    bad = json.dumps({"summary": "x", "confidence": "not-a-number"})
    with pytest.raises(GoalsError) as exc:
        _load_json_model(bad, None, Evidence)
    message = str(exc.value)
    assert "summary" in message  # the extra key
    assert "confidence" in message  # the type error, not dropped


# --- E1a: `goals next --json` exposes the evidence schema before authoring --- #
def test_next_json_emits_evidence_schema(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["next", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "verifications" in data["evidence_fields"]
    assert "acceptance_met" in data["evidence_fields"]
    assert "summary" not in data["evidence_fields"]
    assert "passed" in data["verification_fields"]
    assert "engine-owned" in data["note"]


def test_next_json_returns_structured_error_when_no_phase(tmp_path: Path, monkeypatch) -> None:
    # --json is a machine API: with no active goal it must emit JSON, not a text error.
    _run(["git", "init", "-b", "feature"], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "T"], tmp_path)
    (tmp_path / "README.md").write_text("# demo\n")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-m", "init"], tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["next", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["current_phase"] is None
    assert "error" in data


# --- E2: recording evidence with agent-set passed/ran prints a notice -------- #
def test_phase_evidence_notices_preset_pass(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    evidence = json.dumps(
        {
            "verifications": [
                {"covers": "P1.C1", "kind": "auto", "command": "true", "passed": True, "ran": True}
            ]
        }
    )
    result = runner.invoke(app, ["phase", "evidence", "P1", evidence])
    assert result.exit_code == 0
    assert "ignored agent-set" in result.output
    assert "goals phase verify" in result.output


# --- E3: the load-bearing falsifier failure explains the auto requirement ---- #
def test_missing_falsifier_message_explains_auto_requirement() -> None:
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(
            verifications=[
                Verification(covers="done", kind="auto", command="true", ran=True, passed=True)
            ]
        ),
    )
    findings = review_phase(phase, load_bearing=[("A-load", "the premise")]).findings
    falsifier = [f for f in findings if f.fact_type == GateFactType.MISSING_FALSIFIER]
    assert falsifier, "expected a MISSING_FALSIFIER finding"
    msg = falsifier[0].message.lower()
    assert "auto" in msg
    assert "manual" in msg  # explains why a manual check doesn't count
    assert "--depends" in falsifier[0].message  # offers the escape hatch


# --- E5: completing a goal nudges the critique retrospective ----------------- #
def test_completion_nudge_mentions_critique() -> None:
    assert "/goals:critique" in COMPLETION_CRITIQUE_NUDGE


def test_phase_accept_surfaces_completion_note(tmp_path: Path, monkeypatch) -> None:
    snapshot = GoalSnapshot(
        goal_id="g",
        objective="o",
        topology=WorktreeLease(
            base_repo=str(tmp_path), base_branch="main", worktree_path=str(tmp_path), branch="b"
        ),
        phases=[Phase(phase_id="P1", title="a", goal="g")],
        current_phase="P1",
    )
    from goals import cli

    monkeypatch.setattr(
        cli,
        "accept_phase",
        lambda *a, **k: PhaseAcceptReport(snapshot=snapshot, completion_note=COMPLETION_CRITIQUE_NUDGE),
    )
    result = runner.invoke(app, ["phase", "accept", "P1"])
    assert result.exit_code == 0
    assert "/goals:critique" in result.output


# --- E4: the handoff explains breakdown != phases ---------------------------- #
def test_handoff_explains_breakdown_is_not_phases(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["next", "--agent", "claude"])
    assert result.exit_code == 0
    assert "fixed arc" in result.output
    assert "goals loop activate" in result.output
