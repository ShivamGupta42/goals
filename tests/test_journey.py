from pathlib import Path

from typer.testing import CliRunner

from goals.cli import app
from goals.dashboard import render_dashboard
from goals.journey import reframe, render_journey_text, sort_assumptions
from goals.models import (
    Assumption,
    Event,
    EventType,
    GoalSnapshot,
    ProblemBreakdown,
    Subproblem,
    WorktreeLease,
)
from goals.portability import build_portable_state, render_goal_markdown
from goals.runtime import default_phases
from goals.storage import EventStore

runner = CliRunner()


def _lease(worktree: Path | None = None) -> WorktreeLease:
    path = str(worktree) if worktree is not None else "/wt"
    return WorktreeLease(
        base_repo=path, base_branch="main", worktree_path=path, branch="goal/demo"
    )


def _snapshot(worktree: Path | None = None, **extra) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Ship the journey",
        topology=_lease(worktree),
        phases=default_phases("Ship the journey"),
        current_phase="P1",
        **extra,
    )


# --------------------------------------------------------------------------- #
# reframe — the audience axis
# --------------------------------------------------------------------------- #
def test_reframe_high_school_returns_base_only() -> None:
    notes = {"college": "because event logs replay", "hobbyist": "open events.jsonl"}
    assert reframe("I store everything in one log.", notes, "high_school") == (
        "I store everything in one log."
    )


def test_reframe_appends_audience_note_when_present() -> None:
    notes = {"college": "an event log makes history replayable."}
    assert reframe("Base.", notes, "college") == "Base. an event log makes history replayable."


def test_reframe_falls_back_to_base_when_note_missing() -> None:
    # No hobbyist note recorded → fall back to the base, never invent one.
    assert reframe("Base.", {"college": "x"}, "hobbyist") == "Base."


# --------------------------------------------------------------------------- #
# reducer — upsert semantics
# --------------------------------------------------------------------------- #
def _store_with_goal(tmp_path: Path) -> EventStore:
    store = EventStore(tmp_path / "goal")
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": _snapshot().model_dump()},
        )
    )
    return store


def test_assumption_and_breakdown_land_on_snapshot(tmp_path: Path) -> None:
    store = _store_with_goal(tmp_path)
    assumption = Assumption(
        assumption_id="A-1", statement="I assume one log is enough.", depends_on=True
    )
    breakdown = ProblemBreakdown(
        breakdown_id="BD-1",
        problem="Make the journey legible",
        subproblems=[Subproblem(statement="persist state", tasks=["event log"])],
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.ASSUMPTION_RECORDED,
            payload={"assumption": assumption.model_dump()},
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.BREAKDOWN_RECORDED,
            payload={"breakdown": breakdown.model_dump()},
        )
    )
    snapshot = store.snapshot()
    assert [a.assumption_id for a in snapshot.assumptions] == ["A-1"]
    assert snapshot.assumptions[0].depends_on is True
    assert [b.breakdown_id for b in snapshot.breakdowns] == ["BD-1"]


def test_reemitting_assumption_upserts_status_without_duplicating(tmp_path: Path) -> None:
    store = _store_with_goal(tmp_path)
    base = Assumption(assumption_id="A-1", statement="I assume X holds.", status="holding")
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.ASSUMPTION_RECORDED,
            payload={"assumption": base.model_dump()},
        )
    )
    flipped = base.model_copy(update={"status": "broken"})
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.ASSUMPTION_RECORDED,
            payload={"assumption": flipped.model_dump()},
        )
    )
    snapshot = store.snapshot()
    assert len(snapshot.assumptions) == 1  # upsert, not append
    assert snapshot.assumptions[0].status == "broken"


def test_old_goal_without_journey_fields_still_loads(tmp_path: Path) -> None:
    # Back-compat: a GOAL_CREATED payload that predates the new fields.
    payload = _snapshot().model_dump()
    payload.pop("assumptions", None)
    payload.pop("breakdowns", None)
    store = EventStore(tmp_path / "goal")
    store.append(
        Event(goal_id="demo", event_type=EventType.GOAL_CREATED, payload={"snapshot": payload})
    )
    snapshot = store.snapshot()  # must not raise
    assert snapshot.assumptions == []
    assert snapshot.breakdowns == []


# --------------------------------------------------------------------------- #
# ordering + plain-text journey
# --------------------------------------------------------------------------- #
def test_sort_assumptions_puts_broken_then_load_bearing_first() -> None:
    holding = Assumption(assumption_id="A-h", statement="h", status="holding")
    broken = Assumption(assumption_id="A-b", statement="b", status="broken")
    validated = Assumption(assumption_id="A-v", statement="v", status="validated", depends_on=True)
    load_bearing = Assumption(
        assumption_id="A-lb", statement="lb", status="holding", depends_on=True
    )
    ordered = [a.assumption_id for a in sort_assumptions([holding, broken, validated, load_bearing])]
    assert ordered[0] == "A-b"  # broken first
    assert ordered.index("A-lb") < ordered.index("A-h")  # load-bearing before incidental


def test_render_journey_text_reframes_for_audience() -> None:
    snapshot = _snapshot(
        assumptions=[
            Assumption(
                assumption_id="A-1",
                statement="One log keeps everything.",
                audience_notes={"hobbyist": "open events.jsonl to see it."},
            )
        ]
    )
    hs = render_journey_text(snapshot, "high_school")
    hob = render_journey_text(snapshot, "hobbyist")
    assert "One log keeps everything." in hs
    assert "open events.jsonl" not in hs
    assert "open events.jsonl" in hob


# --------------------------------------------------------------------------- #
# dashboard rendering
# --------------------------------------------------------------------------- #
def test_dashboard_renders_journey_with_toggle_and_broken_first(tmp_path: Path) -> None:
    snapshot = _snapshot(
        worktree=tmp_path,
        assumptions=[
            Assumption(
                assumption_id="A-hold",
                statement="A holding assumption.",
                status="holding",
                depends_on=True,
            ),
            Assumption(
                assumption_id="A-broke",
                statement="A broken assumption.",
                status="broken",
                audience_notes={"college": "here is the deeper why."},
            ),
        ],
        breakdowns=[
            ProblemBreakdown(
                breakdown_id="BD-1",
                phase_id="P1",
                problem="Make it legible",
                pause_note="Checked I wasn't just satisficing.",
                subproblems=[
                    Subproblem(
                        statement="persist state",
                        tasks=["event log"],
                        open_questions=["what if two agents write?"],
                    )
                ],
            )
        ],
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    assert "The building journey" in text
    assert "A holding assumption." in text
    # Accessible, JS-free audience toggle: a named radio group with a programmatic
    # group label, native keyboard-operable radios, and per-option labels.
    assert 'role="radiogroup"' in text
    assert 'aria-label="Explain it like"' in text
    assert 'name="aud"' in text
    assert 'id="aud-hs"' in text and "checked" in text
    assert '<label for="aud-college">' in text
    # Audience note carried for CSS reveal (hidden by default, no JS needed).
    assert 'class="note-college"' in text
    assert "here is the deeper why." in text
    # Breakdown details surfaced in plain language.
    assert "Make it legible" in text
    assert "what if two agents write?" in text
    assert "load-bearing" in text
    # Broken assumption appears before the holding one in source order.
    assert text.index("A broken assumption.") < text.index("A holding assumption.")


def test_dashboard_hides_journey_when_no_trace(tmp_path: Path) -> None:
    output = tmp_path / "dashboard.html"
    render_dashboard(_snapshot(worktree=tmp_path), output)
    assert "The building journey" not in output.read_text()


# --------------------------------------------------------------------------- #
# portability — survives agent handoff
# --------------------------------------------------------------------------- #
def test_portable_state_includes_journey() -> None:
    snapshot = _snapshot(
        assumptions=[Assumption(assumption_id="A-1", statement="s", toward="Y", depends_on=True)],
        breakdowns=[ProblemBreakdown(breakdown_id="BD-1", problem="P")],
    )
    state = build_portable_state(snapshot)
    assert state["assumptions"][0]["id"] == "A-1"
    assert state["assumptions"][0]["depends_on"] is True
    assert state["breakdowns"][0]["problem"] == "P"


def test_goal_markdown_shows_assumptions() -> None:
    snapshot = _snapshot(
        assumptions=[
            Assumption(assumption_id="A-1", statement="One log is enough.", depends_on=True)
        ]
    )
    md = render_goal_markdown(snapshot)
    assert "Building journey" in md
    assert "One log is enough." in md
    assert "load-bearing" in md


# --------------------------------------------------------------------------- #
# CLI — in-process
# --------------------------------------------------------------------------- #
def _repo_with_goal(path: Path) -> None:
    import subprocess

    def run(cmd):
        subprocess.run(cmd, cwd=path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    run(["git", "init", "-b", "feature"])
    run(["git", "config", "user.email", "t@example.com"])
    run(["git", "config", "user.name", "T"])
    (path / "README.md").write_text("# demo\n")
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "init"])
    from goals.runtime import create_goal

    create_goal("ship the journey", path, workspace="in_place")


def test_cli_assess_assume_and_journey(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "assess",
            "assume",
            "I assume one log is enough.",
            "--toward",
            "durable state",
            "--depends",
            "--hobbyist",
            "open events.jsonl.",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Recorded assumption" in result.stdout

    journey = runner.invoke(app, ["assess", "journey", "--audience", "hobbyist"])
    assert journey.exit_code == 0, journey.stdout
    assert "I assume one log is enough." in journey.stdout
    assert "open events.jsonl." in journey.stdout


def test_cli_assess_breakdown_rejects_malformed_json(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["assess", "breakdown", "{not valid json"])
    # A user-input error must surface as a clean message, not a raw traceback.
    assert result.exit_code == 1
    assert "Invalid JSON" in result.stdout
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_cli_assess_breakdown_rejects_invalid_schema(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    # Valid JSON, but missing the required `problem` field.
    result = runner.invoke(app, ["assess", "breakdown", '{"whys": []}'])
    assert result.exit_code == 1
    assert "Invalid ProblemBreakdown" in result.stdout


def test_cli_assess_breakdown_rejects_missing_file(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    # A bad --file path must be a clean error, not a raw FileNotFoundError.
    result = runner.invoke(app, ["assess", "breakdown", "--file", "no_such_file.json"])
    assert result.exit_code == 1
    assert "Could not read" in result.stdout
    assert result.exception is None or isinstance(result.exception, SystemExit)
