"""`goals metrics`: a read-only report built from the goals' own event logs."""

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from goals.cli import app
from goals.metrics import (
    build_metrics_report,
    find_goal_logs,
    render_metrics_report,
    summarize_log,
)

runner = CliRunner()
SRC = Path(__file__).resolve().parents[1] / "src" / "goals"
ROOT = SRC.parents[1]


def _event(kind: str, payload: dict | None = None, ts: str = "2026-06-01T00:00:00+00:00") -> dict:
    return {
        "event_id": str(uuid4()),
        "goal_id": "g",
        "event_type": kind,
        "timestamp": ts,
        "payload": payload if payload is not None else {},
    }


def _review(phase: str, verdict: str, p0: list[str] | None = None, ts: str = "") -> dict:
    gate = {"verdict": verdict, "p0": p0 or [], "summary": "s"}
    return _event(
        "phase_reviewed",
        {"phase_id": phase, "gate_result": gate},
        ts or "2026-06-01T01:00:00+00:00",
    )


def _evidence(phase: str, kinds: list[str]) -> dict:
    checks = [{"verification_id": f"V{i}", "kind": kind} for i, kind in enumerate(kinds)]
    return _event("phase_evidence", {"phase_id": phase, "evidence": {"verifications": checks}})


def _checked(phase: str, kinds: list[str]) -> list[dict]:
    """Evidence with these checks, then the engine's verify event for every auto check."""
    ran = [
        {"verification_id": f"V{i}", "ran": True, "passed": True}
        for i, kind in enumerate(kinds)
        if kind == "auto"
    ]
    return [
        _evidence(phase, kinds),
        _event("phase_verified", {"phase_id": phase, "verifications": ran}),
    ]


def _write_log(root: Path, goal: str, events: list) -> Path:
    goal_dir = root / ".agent-workflow" / "goals" / goal
    goal_dir.mkdir(parents=True)
    path = goal_dir / "events.jsonl"
    lines = [e if isinstance(e, str) else json.dumps(e) for e in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(path: Path) -> None:
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "T")
    (path / "README.md").write_text("# demo\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
        digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


# --- one log -------------------------------------------------------------- #
def test_summarize_counts_first_review_attempts_and_proof(tmp_path: Path) -> None:
    log = _write_log(
        tmp_path,
        "demo",
        [
            _event("goal_created", ts="2026-06-01T00:00:00+00:00"),
            *_checked("P1", ["auto", "manual"]),
            _review("P1", "fail", ["proof check was not set up"]),
            *_checked("P1", ["auto", "auto"]),  # later evidence replaces earlier for the phase
            _review("P1", "pass"),
            _review("P2", "pass"),
            _review("P3", "needs_human", ["waiting on you"]),
            _event("user_message_recorded", ts="2026-06-03T00:00:00+00:00"),
        ],
    )
    m = summarize_log(log)

    assert m.goal == "demo"
    assert m.first_event.startswith("2026-06-01") and m.last_event.startswith("2026-06-03")
    assert m.phases_reviewed == 3
    assert m.first_review_passed == 1  # P2 only: P1 failed first, P3 needs a human
    assert m.first_review_by_phase == {"P1": "fail", "P2": "pass", "P3": "needs_human"}
    assert m.review_attempts == 4
    assert m.review_verdicts == {"fail": 1, "pass": 2, "needs_human": 1}
    assert m.proof_kinds == {"auto": 2}  # latest evidence of P1 only
    assert m.proof_recorded is True
    assert m.user_replies == 1
    assert [(r.phase, r.verdict) for r in m.non_pass_reviews] == [
        ("P1", "fail"),
        ("P3", "needs_human"),
    ]
    assert m.non_pass_reviews[0].reason == "proof check was not set up"


def test_old_format_log_is_reported_not_a_crash(tmp_path: Path) -> None:
    """Falsifier for A-1e121416: older logs with fewer fields must not break the report."""
    log = _write_log(
        tmp_path,
        "old-goal",
        [
            _event("goal_created"),
            _event("phase_reviewed", {"phase_id": "P1"}),  # no gate_result at all
            _event("phase_reviewed", {"phase_id": "P2", "gate_result": {"verdict": "pass"}}),
            _event("phase_evidence", {"phase_id": "P2", "evidence": {}}),  # no verifications
            _event("phase_evidence", {"phase_id": "P3"}),  # no evidence at all
            "this line is not json",
            "[1, 2, 3]",  # json, but not an event
            {"event_type": "phase_reviewed"},  # no payload, no timestamp
        ],
    )
    m = summarize_log(log)

    assert m.phases_reviewed == 1
    assert m.first_review_passed == 1
    assert m.proof_recorded is False
    assert m.proof_kinds == {}
    assert m.skipped_lines == 4  # two lines that are not events, two reviews with no verdict
    report = build_metrics_report(tmp_path)
    text = render_metrics_report(report)
    assert "not recorded" in text
    assert "skipped" in text.lower()


def test_unreadable_log_is_listed_and_does_not_stop_the_others(tmp_path: Path) -> None:
    _write_log(tmp_path, "good", [_review("P1", "pass")])
    bad = tmp_path / ".agent-workflow" / "goals" / "bad"
    bad.mkdir(parents=True)
    (bad / "events.jsonl").write_bytes(b"\xff\xfe\x00 not utf-8 \xff\n")

    report = build_metrics_report(tmp_path)

    assert [g.goal for g in report.goals] == ["good"]
    assert len(report.unreadable) == 1 and "bad" in report.unreadable[0]
    assert "bad" in render_metrics_report(report)


# --- finding logs --------------------------------------------------------- #
def test_finds_goals_in_this_folder_and_in_separate_working_folders(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()
    _init_repo(main)
    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "-b", "goal/x", str(linked))
    _write_log(main, "in-main", [_review("P1", "pass")])
    _write_log(linked, "in-linked", [_review("P1", "fail", ["x"])])

    for start in (main, linked):  # same answer from either folder
        found = {p.parent.name for p in find_goal_logs(start)}
        assert found == {"in-main", "in-linked"}

    report = build_metrics_report(linked)
    assert report.totals.goals == 2
    assert report.totals.first_review_by_phase == {"P1": {"reviewed": 2, "passed": 1}}


def test_works_outside_git_and_with_no_goals(tmp_path: Path) -> None:
    assert find_goal_logs(tmp_path) == []
    report = build_metrics_report(tmp_path)
    assert report.totals.goals == 0
    assert "no goals" in render_metrics_report(report).lower()

    _write_log(tmp_path, "plain-folder", [_review("P1", "pass")])
    assert [p.parent.name for p in find_goal_logs(tmp_path)] == ["plain-folder"]


# --- totals and wording --------------------------------------------------- #
def test_totals_add_up_across_goals_and_say_what_they_cannot_tell(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        "a",
        [
            *_checked("P1", ["auto", "auto", "manual"]),
            _review("P1", "pass"),
            _review("P2", "fail", ["x"]),
        ],
    )
    _write_log(tmp_path, "b", [_review("P1", "fail", ["y"]), _review("P1", "pass")])
    _write_log(tmp_path, "c", [_review("P1", "pass")])  # no check kinds recorded

    t = build_metrics_report(tmp_path).totals

    assert t.goals == 3
    assert t.phases_reviewed == 4
    assert t.first_review_passed == 2
    assert t.first_review_by_phase == {
        "P1": {"reviewed": 3, "passed": 2},
        "P2": {"reviewed": 1, "passed": 0},
    }
    assert t.review_attempts == 5
    assert t.review_verdicts == {"pass": 3, "fail": 2}
    assert t.proof_kinds == {"auto": 2, "manual": 1}
    assert t.goals_without_proof_kinds == 2

    text = render_metrics_report(build_metrics_report(tmp_path))
    assert "2 of 3 passed first time" in text  # P1
    assert "run by the engine" in text and "by hand" in text
    assert "does not tell you" in text


# --- read-only ------------------------------------------------------------ #
def test_building_and_printing_the_report_changes_nothing(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()
    _init_repo(main)
    _write_log(main, "g", [*_checked("P1", ["auto"]), _review("P1", "pass"), "junk line"])
    before = _tree_hash(main)

    render_metrics_report(build_metrics_report(main))

    assert _tree_hash(main) == before


def test_command_plain_and_json_leave_the_folder_untouched(tmp_path: Path, monkeypatch) -> None:
    main = tmp_path / "main"
    main.mkdir()
    _init_repo(main)
    _write_log(main, "g", [*_checked("P1", ["auto"]), _review("P1", "pass")])
    monkeypatch.chdir(main)
    before = _tree_hash(main)

    plain = runner.invoke(app, ["metrics"])
    as_json = runner.invoke(app, ["metrics", "--json"])

    assert plain.exit_code == 0, plain.output
    assert "1 of 1 passed first time" in plain.output
    assert as_json.exit_code == 0, as_json.output
    data = json.loads(as_json.stdout)
    assert data["totals"]["goals"] == 1
    assert data["goals"][0]["goal"] == "g"
    assert _tree_hash(main) == before


# --- who sees the numbers ------------------------------------------------- #
def _cli_functions_using_metrics() -> set[str]:
    names = {"build_metrics_report", "render_metrics_report", "summarize_log", "find_goal_logs"}
    tree = ast.parse((SRC / "cli.py").read_text())
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(node))
    }


def test_metrics_is_not_wired_into_anything_an_agent_reads() -> None:
    """The agent must not see these numbers in its prompts, so it cannot aim at them."""
    importers = [
        p.name
        for p in SRC.rglob("*.py")
        if p.name not in {"metrics.py", "cli.py"}
        and ("goals.metrics" in p.read_text() or "import metrics" in p.read_text())
    ]
    assert importers == []
    # cli.py also prints what the agent reads (next, check, brief, the hooks): only the
    # `metrics` command itself may use the report.
    assert _cli_functions_using_metrics() == {"metrics"}

    prompt_files = [
        ROOT / "AGENTS.md",
        *(ROOT / "commands").glob("*.md"),
        *(ROOT / "skills").rglob("*.md"),
    ]
    hits = [p.name for p in prompt_files if "goals metrics" in p.read_text()]
    assert hits == []


# --- reviewer findings: odd input, wording, order ------------------------- #
def test_separator_characters_inside_an_event_do_not_split_it(tmp_path: Path) -> None:
    """The engine writes U+2028 raw inside a JSON string; str.splitlines() would cut it in two."""
    goal_dir = tmp_path / ".agent-workflow" / "goals" / "sep"
    goal_dir.mkdir(parents=True)
    lines = [
        json.dumps(_review("P1", "fail", ["a\u2028b"]), ensure_ascii=False),
        json.dumps(_event("user_message_recorded", {"text": "x\u2029y\x85z"}), ensure_ascii=False),
        json.dumps(_review("P1", "pass"), ensure_ascii=False),
    ]
    assert any("\u2028" in line for line in lines)
    (goal_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    m = summarize_log(goal_dir / "events.jsonl")

    assert m.first_review_by_phase == {"P1": "fail"}
    assert m.review_attempts == 2
    assert m.user_replies == 1
    assert m.skipped_lines == 0


def test_an_auto_check_the_engine_never_ran_is_not_counted_as_run(tmp_path: Path) -> None:
    partly = _write_log(
        tmp_path,
        "partly",
        [
            _evidence("P1", ["auto", "auto", "manual"]),
            _event(
                "phase_verified",
                {"phase_id": "P1", "verifications": [{"verification_id": "V0", "ran": True}]},
            ),
        ],
    )
    fresh = _write_log(
        tmp_path,
        "fresh",
        [*_checked("P1", ["auto"]), _evidence("P1", ["auto"])],  # new evidence, not verified yet
    )

    assert summarize_log(partly).proof_kinds == {"auto": 1, "not_run": 1, "manual": 1}
    assert summarize_log(fresh).proof_kinds == {"not_run": 1}
    assert "declared but not run" in render_metrics_report(build_metrics_report(tmp_path))


def test_a_goal_with_no_checks_is_not_called_an_old_log(tmp_path: Path) -> None:
    _write_log(tmp_path, "brand-new", [_event("goal_created")])
    _write_log(tmp_path, "emptied", [*_checked("P1", ["auto"]), _evidence("P1", [])])
    _write_log(tmp_path, "with-checks", _checked("P1", ["auto"]))

    text = render_metrics_report(build_metrics_report(tmp_path))

    assert "older logs" not in text
    assert "2 goal(s) have no checks recorded" in text
    assert not any(line.rstrip().endswith("checks:") for line in text.splitlines())
    assert "checks: not recorded" in text


def test_damaged_lines_cannot_crash_the_report_or_printing(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        "damaged",
        [
            "[" * 200_000,  # deep enough to overflow the JSON parser's recursion
            '{"event_type": "phase_reviewed", "payload": {"phase_id": "P1", "gate_result": '
            '{"verdict": "fail", "p0": ["broken \\ud800 character"]}}}',
            _review("P1", "pass"),
        ],
    )

    report = build_metrics_report(tmp_path)
    text = render_metrics_report(report)

    text.encode("utf-8")  # printing must not raise
    report.model_dump_json().encode("utf-8")  # nor --json
    assert report.goals[0].skipped_lines == 1
    assert report.goals[0].first_review_by_phase == {"P1": "fail"}


def test_phases_are_in_natural_order_and_goals_oldest_first(tmp_path: Path) -> None:
    _write_log(
        tmp_path,
        "a-newer",
        [_review("P10", "pass", ts="2026-07-02T00:00:00+00:00"), _review("P2", "pass")],
    )
    _write_log(
        tmp_path,
        "z-older",
        [
            _event("goal_created", ts="2026-06-01T00:00:00+00:00"),
            _review("P1", "pass", ts="2026-06-01T01:00:00+00:00"),
        ],
    )

    report = build_metrics_report(tmp_path)

    assert [g.goal for g in report.goals] == ["z-older", "a-newer"]
    assert list(report.totals.first_review_by_phase) == ["P1", "P2", "P10"]
    phases_in_text = [
        ln.strip().split(":")[0]
        for ln in render_metrics_report(report).splitlines()
        if ln.strip().startswith("P")
    ]
    assert phases_in_text == ["P1", "P2", "P10"]


def test_a_long_list_of_failed_reviews_is_cut_with_a_count(tmp_path: Path) -> None:
    _write_log(tmp_path, "many", [_review(f"P{n}", "fail", [f"reason {n}"]) for n in range(1, 13)])

    text = render_metrics_report(build_metrics_report(tmp_path))

    assert "Reviews that did not pass (12)" in text
    assert text.count(" fail: reason ") == 10
    assert "(+2 more; see --json)" in text


def test_automatic_notices_are_not_counted_as_user_replies(tmp_path: Path) -> None:
    """Older logs hold host notices the hook stored as if the user typed them."""
    notice = "<task-notification>\n<task-id>b1</task-id>\n</task-notification>"
    log = _write_log(
        tmp_path,
        "notices",
        [
            _event("goal_created"),
            _event("user_message_recorded", {"message": {"text": "yes"}}),
            _event("user_message_recorded", {"message": {"text": notice}}),
            _event("user_message_recorded", {"message": {"text": "why <task-notification>?"}}),
            _event("user_message_recorded", {"message": "odd shape"}),  # still a stored reply
        ],
    )

    assert summarize_log(log).user_replies == 3
