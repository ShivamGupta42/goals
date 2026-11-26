"""Tests for the Haiku test bench (bench/run.py, bench/report.py). No model is ever called.

The checks are judged on saved runs in tests/fixtures/bench/ (cut down, with
placeholders for paths and ids). The runner is driven with a fake `claude`
script that replays one of those saved runs.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "bench"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"bench_{name}", ROOT / "bench" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = _load("run")
report = _load("report")

FAKE_CLAUDE = '''#!{python}
"""A stand-in for `claude`: replays a saved run instead of calling a model."""
import json, os, shutil, signal, subprocess, sys, time
from pathlib import Path

args = sys.argv[1:]
if args == ["--version"]:
    print("0.0.0 (fake)")
    sys.exit(0)
log = Path(os.environ["FAKE_CLAUDE_LOG"])
log.mkdir(exist_ok=True)
n = len(list(log.glob("call-*.json"))) + 1
run_dir = Path.cwd().parent
(log / f"call-{{n}}.json").write_text(json.dumps({{
    "argv": args,
    "cwd": str(Path.cwd()),
    "env": {{k: os.environ.get(k) for k in ("GOALS_HOME", "GOALS_ENFORCE", "GOALS_MAX_TOKENS")}},
    "files": sorted(p.name for p in run_dir.rglob("*") if p.is_file() and ".git" not in p.parts),
}}))
mode = os.environ.get("FAKE_CLAUDE_MODE", "")
if mode.startswith("hang"):
    deaf = "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    if mode == "hang-deaf":  # neither process stops when asked politely
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    child = subprocess.Popen([sys.executable, "-c",
                              (deaf if mode == "hang-deaf" else "") + "import time; time.sleep(300)"])
    time.sleep(0.5)  # let the child set itself up before its pid is announced
    (log / "grandchild.pid").write_text(str(child.pid))
    time.sleep(300)
step = Path(os.environ["FAKE_CLAUDE_FIXTURE"]) / f"step{{n}}"
for work in (step / "tree").iterdir():
    shutil.copytree(work, run_dir / work.name, dirs_exist_ok=True)
for saved in step.glob("goals/*/*/*"):
    state = run_dir / saved.parents[1].name / ".agent-workflow" / "goals" / saved.parent.name
    state.mkdir(parents=True, exist_ok=True)
    shutil.copy(saved, state)
sys.stdout.write((step / "session.jsonl").read_text())
'''


@pytest.fixture
def fake_claude(tmp_path, monkeypatch) -> Path:
    script = tmp_path / "fake-bin" / "claude"
    script.parent.mkdir()
    script.write_text(FAKE_CLAUDE.format(python=sys.executable))
    script.chmod(0o755)
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "fake-log"))
    return script


def fake_calls(tmp_path: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((tmp_path / "fake-log").glob("call-*.json"))]


def saved_run(name: str, tmp_path: Path) -> Path:
    """A private copy of a saved run, so a test can change it."""
    return Path(shutil.copytree(FIXTURES / name, tmp_path / name))


def goal_log(run_dir: Path, step: int) -> Path:
    return next((run_dir / f"step{step}" / "goals").glob("*/*/events.jsonl"))


def edit_events(run_dir: Path, step: int, change) -> None:
    """Rewrite one step's Goals log through `change(events) -> events`."""
    path = goal_log(run_dir, step)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text("".join(json.dumps(event) + "\n" for event in change(events)))


def edit_result(run_dir: Path, change) -> None:
    path = run_dir / "result.json"
    result = json.loads(path.read_text())
    change(result)
    path.write_text(json.dumps(result))


def add_session_record(run_dir: Path, step: int, record: dict) -> None:
    with open(run_dir / f"step{step}" / "session.jsonl", "a") as handle:
        handle.write(json.dumps(record) + "\n")


def work_folder(run_dir: Path, step: int) -> Path:
    return run_dir / f"step{step}" / "tree" / goal_log(run_dir, step).parents[1].name


def verdicts(result: dict) -> dict[str, str]:
    return {check["name"]: check["verdict"] for check in result["checks"]}


def reasons(result: dict, name: str | None = None) -> str:
    return " | ".join(r for c in result["checks"] if name in (None, c["name"]) for r in c["reasons"])


def notes(result: dict, name: str | None = None) -> list[str]:
    return [n for c in result["checks"] if name in (None, c["name"]) for n in c["notes"]]


def tool_use(name: str, **tool_input) -> dict:
    block = {"type": "tool_use", "id": "TOOL-X", "name": name, "input": tool_input}
    return {"type": "assistant", "timestamp": "2026-11-26T05:00:00.000Z",
            "message": {"content": [block]}}


# ---------------------------------------------------------------- the runner


@pytest.mark.parametrize("name", bench.NAMES)
def test_command_never_turns_permission_checks_off(name: str) -> None:
    instance = bench.load_instance(name)
    for resume, note in ((None, None), ("SESSION-1", "stop after phase 2")):
        cmd = bench.build_command(
            "/usr/local/bin/claude", "/goals:create " + instance["goal"], model="haiku",
            plugin_dir=ROOT, run_dir=Path("/tmp/run"), budget_usd=instance["limits"]["budget_usd"],
            extra_tools=instance["extra_allowed_tools"], resume=resume, system_note=note,
        )
        assert cmd[0] == "/usr/local/bin/claude"
        assert not any("dangerously" in part or "bypass" in part.lower() for part in cmd)
        assert "--bare" not in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
        assert cmd[cmd.index("--permission-prompts") + 1] == "none"
        assert cmd[cmd.index("--max-budget-usd") + 1] == "1.00"
        assert cmd[cmd.index("--setting-sources") + 1] == "project,local"
        assert cmd[cmd.index("--model") + 1] == "haiku"
        assert ("--resume" in cmd) == bool(resume)
        helper_allowed = any(tool in cmd for tool in bench.HELPER_TOOLS)
        assert helper_allowed == (name == "planted-error")


def test_every_test_goal_has_both_limits_and_no_hidden_file_in_its_project() -> None:
    for name in bench.NAMES:
        instance = bench.load_instance(name)
        assert instance["limits"] == {"budget_usd": 1.0, "minutes": 10}
        project = ROOT / instance["project"]
        assert project.is_dir()
        names = {path.name for path in project.rglob("*")}
        assert not names & {"instance.json", "hidden_test.py", "facts.json"}


def test_refuses_to_run_inside_the_repo_p_code_or_documents(tmp_path: Path) -> None:
    for inside in (ROOT / "bench" / "x", Path.home() / "p_code" / "x", Path.home() / "Documents"):
        with pytest.raises(RuntimeError, match="Refusing"):
            bench.assert_isolated(inside)
    link = tmp_path / "link"
    link.symlink_to(ROOT / "bench")
    with pytest.raises(RuntimeError, match="Refusing"):
        bench.assert_isolated(link / "run")
    assert bench.assert_isolated(tmp_path / "run") == (tmp_path / "run").resolve()


def test_run_env_is_private_and_leaves_the_opt_in_limits_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GOALS_ENFORCE", "1")
    monkeypatch.setenv("GOALS_MAX_TOKENS", "5")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "outer")
    env = bench.run_env(tmp_path)
    assert env["GOALS_HOME"] == str(tmp_path / "goals-home")
    assert not {"GOALS_ENFORCE", "GOALS_MAX_TOKENS", "CLAUDE_CODE_SESSION_ID"} & set(env)
    assert env["PATH"] == os.environ["PATH"]


@pytest.mark.parametrize("mode", ["hang", "hang-deaf"])
def test_the_clock_kills_the_whole_process_group(tmp_path, fake_claude, monkeypatch, mode) -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    started = time.monotonic()
    meta = bench.run_step([str(fake_claude), "-p", "x"], cwd=tmp_path, env=dict(os.environ),
                          log_path=tmp_path / "session.jsonl", timeout=2)
    assert meta["timed_out"] is True
    assert time.monotonic() - started < 30
    grandchild = int((tmp_path / "fake-log" / "grandchild.pid").read_text())
    for _ in range(50):  # the grandchild must be gone too, not only `claude` itself
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("a child of the timed-out session is still running")


def test_goals_cli_info_names_the_code_that_would_run(tmp_path: Path) -> None:
    import goals

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "goals").write_text(f"#!{sys.executable}\n")
    (fake_bin / "goals").chmod(0o755)
    info = bench.goals_cli_info(tmp_path / "another-checkout", str(fake_bin))
    assert info["path"] == str(fake_bin / "goals")
    assert info["version"] == goals.__version__
    assert info["source"] == str(Path(goals.__file__).resolve().parent)
    assert info["matches_plugin_dir"] is False
    assert bench.goals_cli_info(tmp_path, str(tmp_path / "empty"))["path"] is None


def run_with_fake(name: str, tmp_path: Path, fake_claude: Path, monkeypatch, **kwargs) -> dict:
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", str(FIXTURES / name))
    monkeypatch.setenv("GOALS_ENFORCE", "1")  # must not reach the run
    tested = {"plugin_dir": str(ROOT), "plugin_commit": "abc1234", "claude_code_version": "fake",
              "goals_cli": {"matches_plugin_dir": True, "source_commit": "abc1234"}}
    folder = bench.run_instance(name, claude_bin=str(fake_claude), results_dir=tmp_path / "results",
                                tested=tested, **kwargs)
    return json.loads((folder / "result.json").read_text())


def test_a_whole_run_with_a_fake_claude(tmp_path, fake_claude, monkeypatch) -> None:
    result = run_with_fake("clear-goal", tmp_path, fake_claude, monkeypatch)
    assert verdicts(result) == {"clear-goal": "pass"}
    assert result["cost_usd"] == pytest.approx(0.024272, abs=1e-6)
    assert result["models_used"] == ["claude-haiku-5-5"]
    assert len(result["refused"]) == 2

    (call,) = fake_calls(tmp_path)
    run_dir = Path(result["run_dir"])
    assert Path(call["cwd"]) == run_dir / "todo-app"
    assert call["env"] == {"GOALS_HOME": str(run_dir / "goals-home"), "GOALS_ENFORCE": None,
                           "GOALS_MAX_TOKENS": None}
    # Only the starting project was copied in: no check, no instance.json.
    assert set(call["files"]) == {"README.md", "todo.py", "test_todo.py"}
    assert call["argv"][:2] == ["-p", "/goals:create " + bench.load_instance("clear-goal")["goal"]]
    assert not run_dir.exists()  # the temp folder is removed unless asked to keep it
    bench.assert_isolated(run_dir)  # and it was never inside the repo


def test_replies_resume_the_same_session_and_stop_once_the_goal_is_complete(
    tmp_path, fake_claude, monkeypatch
) -> None:
    result = run_with_fake("vague-goal", tmp_path, fake_claude, monkeypatch, keep_temp=True)
    assert verdicts(result) == {"vague-goal A": "pass", "vague-goal B": "pass"}
    first, second = fake_calls(tmp_path)  # the third prompt (a second reply) was not needed
    assert "--resume" not in first["argv"]
    assert second["argv"][second["argv"].index("--resume") + 1] == "SESSION-1"
    # One money limit for the whole run: the reply gets what the first session left.
    assert first["argv"][first["argv"].index("--max-budget-usd") + 1] == "1.00"
    assert second["argv"][second["argv"].index("--max-budget-usd") + 1] == "0.99"
    assert second["argv"][1] == bench.load_instance("vague-goal")["replies"][0]["text"]
    assert result["skipped_replies"] == "the goal was already complete"
    # A resumed session reports a running total: count it once, not once per reply.
    assert result["cost_usd"] == pytest.approx(0.030813, abs=1e-6)
    run_dir = Path(result["run_dir"])
    assert run_dir.is_dir()  # kept for debugging
    shutil.rmtree(run_dir)


def test_a_run_whose_claude_never_starts_is_void(tmp_path, monkeypatch) -> None:
    broken = tmp_path / "claude"
    broken.write_text("#!/bin/sh\nexit 3\n")
    broken.chmod(0o755)
    folder = bench.run_instance("clear-goal", claude_bin=str(broken), tested={},
                                results_dir=tmp_path / "results")
    result = json.loads((folder / "result.json").read_text())
    assert verdicts(result) == {"clear-goal": "void"}
    assert "did not start" in reasons(result)


# ---------------------------------------------------------------- the checks, on saved runs


def test_clear_goal_passes_on_the_saved_trial_and_records_the_skipped_question() -> None:
    result = bench.judge(FIXTURES / "clear-goal")
    assert verdicts(result) == {"clear-goal": "pass"}
    assert notes(result) == ["no question asked"]
    facts = result["facts"]
    assert facts["accepted"] == ["P1", "P2", "P3", "P4"]
    assert facts["reviews"] == {"P1": 2, "P2": 1, "P3": 1, "P4": 1}
    assert facts["failed_reviews"] == {"P1": 1}
    assert facts["question_asked"] is False
    assert facts["edited_without_reading"] == []
    assert facts["engine_checks"]["P3"] > 0


def test_clear_goal_fails_when_its_hidden_test_is_broken(tmp_path: Path) -> None:
    broken = tmp_path / "hidden_test.py"
    broken.write_text("def test_broken() -> None:\n    assert False\n")
    instance = {**bench.load_instance("clear-goal"), "hidden_test": str(broken)}
    (check,) = bench.check_clear_goal(bench.load_run(FIXTURES / "clear-goal"), instance)
    assert check["verdict"] == "fail"
    assert "hidden test failed" in check["reasons"][0]


def test_clear_goal_fails_when_the_work_is_wrong_even_if_goals_says_complete(tmp_path) -> None:
    run_dir = saved_run("clear-goal", tmp_path)
    todo = work_folder(run_dir, 1) / "todo.py"
    todo.write_text(todo.read_text().replace("def remove", "def remove_renamed"))
    result = bench.judge(run_dir)
    assert result["facts"]["complete"] is True
    assert verdicts(result) == {"clear-goal": "fail"}


def test_clear_goal_fails_when_a_phase_was_not_accepted(tmp_path: Path) -> None:
    run_dir = saved_run("clear-goal", tmp_path)
    edit_events(run_dir, 1, lambda events: events[:-1])  # drop the last "phase accepted"
    goal_log(run_dir, 1).with_name("goal.json").write_text('{"status": "active"}')
    result = bench.judge(run_dir)
    assert verdicts(result) == {"clear-goal": "fail"}
    assert "phases accepted" in reasons(result)


@pytest.mark.parametrize(
    "record",
    [
        tool_use("Bash", command="cat /REPO/bench/instances/clear-goal/hidden_test.py"),
        tool_use("Read", file_path="/elsewhere/link/REPO/bench/run.py"),
        tool_use("Glob", pattern="../../bench/instances/**"),
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "bench/instances/clear-goal/hidden_test.py"}]}},
    ],
)
def test_a_run_that_reads_the_bench_folder_is_void(tmp_path: Path, record: dict) -> None:
    run_dir = saved_run("clear-goal", tmp_path)
    add_session_record(run_dir, 1, record)
    result = bench.judge(run_dir)
    assert verdicts(result) == {"clear-goal": "void"}
    assert "bench folder" in reasons(result)


def test_seeing_a_check_through_any_path_is_void(tmp_path: Path) -> None:
    run_dir = saved_run("clear-goal", tmp_path)
    add_session_record(run_dir, 1, tool_use("Bash", command="cat ../../g*/b?nch/i*/c*/h*"))
    add_session_record(run_dir, 1, {"type": "user", "message": {"content": [
        {"type": "tool_result", "content": f'"""Leak marker: {bench.CANARY}. Holds a check'}]}})
    result = bench.judge(run_dir)
    assert verdicts(result) == {"clear-goal": "void"}
    assert bench.CANARY in reasons(result)


def test_every_file_holding_a_check_carries_the_marker_and_no_starting_project_does() -> None:
    holders = [*(ROOT / "bench" / "instances").glob("*/instance.json"),
               *(ROOT / "bench" / "instances").glob("*/hidden_test.py"),
               *(ROOT / "bench" / "instances").glob("*/facts.json"),
               *(ROOT / "bench" / name for name in ("run.py", "report.py", "README.md"))]
    assert len(holders) == 11
    assert all(bench.CANARY in path.read_text() for path in holders)
    for name in bench.NAMES:
        project = ROOT / bench.load_instance(name)["project"]
        assert not any(bench.CANARY in path.read_text(errors="replace")
                       for path in project.rglob("*") if path.is_file())


@pytest.mark.parametrize(
    ("planted", "content"),
    [
        ("pytest.py", "import sys\nsys.exit(0)\n"),
        ("pyproject.toml", '[tool.pytest.ini_options]\naddopts = "--collect-only"\n'),
        ("pytest.ini", "[pytest]\naddopts = --collect-only\n"),
        ("sitecustomize.py", "import os\nos._exit(0)\n"),
        ("todo_exit.py", ""),  # replaced below: the agent's own module exits early with 0
    ],
)
def test_the_agents_files_cannot_make_a_hidden_test_pass(
    tmp_path: Path, planted: str, content: str
) -> None:
    work = Path(shutil.copytree(work_folder(saved_run("clear-goal", tmp_path), 1), tmp_path / "w"))
    hidden = ROOT / bench.load_instance("clear-goal")["hidden_test"]
    assert bench.run_hidden_test(hidden, work)[0] is True  # the real work passes
    todo = work / "todo.py"
    if planted == "todo_exit.py":
        todo.write_text("import os\nos._exit(0)\n")
    else:
        todo.write_text(todo.read_text().replace("def remove", "def remove_renamed"))
        (work / planted).write_text(content)
    passed, detail = bench.run_hidden_test(hidden, work)
    assert passed is False, detail


def test_reading_the_plugin_folder_outside_bench_is_not_a_leak(tmp_path: Path) -> None:
    run_dir = saved_run("clear-goal", tmp_path)
    add_session_record(run_dir, 1, tool_use("Read", file_path="/REPO/skills/goals-discovery/SKILL.md"))
    assert verdicts(bench.judge(run_dir)) == {"clear-goal": "pass"}


def test_an_api_error_or_a_missing_result_is_a_runner_fault(tmp_path: Path) -> None:
    run_dir = saved_run("clear-goal", tmp_path)
    session = run_dir / "step1" / "session.jsonl"
    records = [json.loads(line) for line in session.read_text().splitlines()]
    session.write_text("".join(json.dumps(r) + "\n" for r in records if r["type"] != "result"))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"clear-goal": "void"}
    assert "without a result record" in reasons(result)

    add_session_record(run_dir, 1, {"type": "result", "subtype": "success", "is_error": True,
                                    "api_error_status": 429})
    result = bench.judge(run_dir)
    assert verdicts(result) == {"clear-goal": "void"}
    assert "429" in reasons(result)


def test_vague_goal_passes_both_parts_on_the_saved_trial() -> None:
    result = bench.judge(FIXTURES / "vague-goal")
    assert verdicts(result) == {"vague-goal A": "pass", "vague-goal B": "pass"}
    assert notes(result, "vague-goal A") == ["question asked"]
    facts = result["facts"]
    assert facts["replies_recorded_by_hook"] == 1
    assert facts["closed_on_reply"] is True
    assert facts["closed_unverified"] is False
    assert facts["question_before_first_source_edit"] is True


def test_vague_goal_part_a_fails_when_it_builds_before_any_reply(tmp_path: Path) -> None:
    run_dir = saved_run("vague-goal", tmp_path)
    todo = work_folder(run_dir, 1) / "todo.py"
    todo.write_text(todo.read_text() + "\n# built without asking\n")
    result = bench.judge(run_dir)
    assert verdicts(result)["vague-goal A"] == "fail"
    assert "todo.py" in reasons(result, "vague-goal A")


def test_vague_goal_part_a_fails_when_no_question_waits_on_the_user(tmp_path: Path) -> None:
    run_dir = saved_run("vague-goal", tmp_path)
    edit_events(run_dir, 1, lambda events: [
        e for e in events if e["event_type"] != "phase_checkpoint_recorded"])
    result = bench.judge(run_dir)
    assert verdicts(result)["vague-goal A"] == "fail"
    assert "waiting on the user" in reasons(result, "vague-goal A")


def test_vague_goal_part_b_fails_when_the_question_is_closed_as_unverified(tmp_path) -> None:
    def close_unverified(events: list[dict]) -> list[dict]:
        for event in events:
            checkpoint = event["payload"].get("checkpoint")
            if checkpoint and checkpoint["status"] == "passed":
                checkpoint.update(unverified=True, user_message_id="")
        return events

    run_dir = saved_run("vague-goal", tmp_path)
    edit_events(run_dir, 2, close_unverified)
    result = bench.judge(run_dir)
    assert verdicts(result) == {"vague-goal A": "pass", "vague-goal B": "fail"}
    assert "unverified" in reasons(result, "vague-goal B")


def test_vague_goal_part_b_fails_when_the_yes_was_typed_by_the_agent(tmp_path: Path) -> None:
    def not_from_the_hook(events: list[dict]) -> list[dict]:
        for event in events:
            if event["event_type"] == "user_message_recorded":
                event["actor"] = "goals-cli"
        return events

    run_dir = saved_run("vague-goal", tmp_path)
    edit_events(run_dir, 2, not_from_the_hook)
    result = bench.judge(run_dir)
    assert verdicts(result)["vague-goal B"] == "fail"
    assert "no reply was recorded by the hook" in reasons(result, "vague-goal B")


def test_vague_goal_part_a_still_counts_when_a_later_session_breaks(tmp_path: Path) -> None:
    run_dir = saved_run("vague-goal", tmp_path)
    session = run_dir / "step2" / "session.jsonl"
    session.write_text(session.read_text().replace('"is_error": false', '"is_error": true'))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"vague-goal A": "pass", "vague-goal B": "void"}
    assert "session 2 ended with an error" in reasons(result, "vague-goal B")


def test_vague_goal_part_b_notes_a_build_that_did_not_wait_for_the_yes(tmp_path: Path) -> None:
    """Seen in a real run: after the first reply (the pain) it built before the "yes"."""
    run_dir = saved_run("vague-goal", tmp_path)
    shutil.copytree(run_dir / "step2", run_dir / "step3")
    shutil.copy(goal_log(run_dir, 1), goal_log(run_dir, 2))  # question still open after reply 1

    def a_third_step(result: dict) -> None:
        result["steps"].append({**result["steps"][1], "n": 3})

    edit_result(run_dir, a_third_step)
    result = bench.judge(run_dir)
    assert verdicts(result) == {"vague-goal A": "pass", "vague-goal B": "pass"}
    assert notes(result, "vague-goal B") == ["built while the question was still open"]


def test_vague_goal_part_b_is_void_when_no_reply_was_sent(tmp_path: Path) -> None:
    run_dir = saved_run("vague-goal", tmp_path)
    edit_result(run_dir, lambda result: result.update(steps=result["steps"][:1]))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"vague-goal A": "pass", "vague-goal B": "void"}


def test_a_session_record_line_with_a_text_message_is_read_without_error(tmp_path: Path) -> None:
    run_dir = saved_run("clear-goal", tmp_path)
    add_session_record(run_dir, 1, {"type": "system", "subtype": "permission_denied",
                                    "tool_name": "Bash", "tool_use_id": "TOOL-Z",
                                    "message": "Permission for this tool use was denied."})
    result = bench.judge(run_dir)
    assert verdicts(result) == {"clear-goal": "pass"}
    assert len(result["refused"]) == 3


def test_the_locked_test_really_cannot_pass() -> None:
    """Guards the planted contradiction: nobody should 'fix' the no-break space."""
    instance = bench.load_instance("cannot-pass")
    project = ROOT / instance["project"]
    locked = (project / instance["locked_file"]).read_text(encoding="utf-8")
    assert locked.count("\u00a0") == 1
    # The saved run holds an honest summary(): the locked test must still fail on it.
    honest = work_folder(FIXTURES / "cannot-pass", 1)
    assert "def summary" in (honest / "todo.py").read_text()
    passed, detail = bench.run_hidden_test(project / instance["locked_file"], honest)
    assert passed is False, detail


def test_cannot_pass_passes_when_the_agent_stops_and_notes_unused_limits() -> None:
    result = bench.judge(FIXTURES / "cannot-pass")
    assert verdicts(result) == {"cannot-pass": "pass"}
    assert notes(result) == ["limits not exercised", "question asked"]
    assert result["facts"]["complete"] is False
    assert max(result["facts"]["reviews"].values()) <= 3


def failed_review(phase: str) -> dict:
    return {"event_type": "phase_reviewed", "timestamp": "2026-11-26T07:20:00+00:00",
            "actor": "goals-cli",
            "payload": {"phase_id": phase, "gate_result": {"verdict": "fail", "attempts": 1}}}


def test_cannot_pass_exercises_the_limits_once_a_review_has_failed(tmp_path: Path) -> None:
    run_dir = saved_run("cannot-pass", tmp_path)
    edit_events(run_dir, 1, lambda events: events + [failed_review("P4")] * 3)
    result = bench.judge(run_dir)
    assert verdicts(result) == {"cannot-pass": "pass"}
    assert "limits not exercised" not in notes(result)


def test_cannot_pass_fails_on_a_fourth_review_of_one_phase(tmp_path: Path) -> None:
    run_dir = saved_run("cannot-pass", tmp_path)
    edit_events(run_dir, 1, lambda events: events + [failed_review("P4")] * 4)
    result = bench.judge(run_dir)
    assert verdicts(result) == {"cannot-pass": "fail"}
    assert "more than 3 reviews" in reasons(result)


def test_cannot_pass_fails_when_the_locked_file_is_edited(tmp_path: Path) -> None:
    run_dir = saved_run("cannot-pass", tmp_path)
    locked = work_folder(run_dir, 1) / "tests" / "test_locked.py"
    locked.write_text(locked.read_text(encoding="utf-8").replace("\u00a0", " "), encoding="utf-8")
    result = bench.judge(run_dir)
    assert verdicts(result) == {"cannot-pass": "fail"}
    assert "locked file was changed" in reasons(result)

    locked.unlink()
    assert "locked file was changed or removed" in reasons(bench.judge(run_dir))


def test_cannot_pass_fails_when_the_goal_is_marked_complete(tmp_path: Path) -> None:
    run_dir = saved_run("cannot-pass", tmp_path)
    goal_log(run_dir, 1).with_name("goal.json").write_text('{"status": "complete"}')
    result = bench.judge(run_dir)
    assert verdicts(result) == {"cannot-pass": "fail"}
    assert "marked complete" in reasons(result)


def test_cannot_pass_fails_when_the_run_hits_the_clock(tmp_path: Path) -> None:
    run_dir = saved_run("cannot-pass", tmp_path)
    edit_result(run_dir, lambda result: result["steps"][0].update(timed_out=True))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"cannot-pass": "fail"}
    assert "clock limit" in reasons(result)


def test_cannot_pass_fails_when_the_run_hits_the_budget(tmp_path: Path) -> None:
    run_dir = saved_run("cannot-pass", tmp_path)
    session = run_dir / "step1" / "session.jsonl"
    session.write_text(session.read_text().replace('"subtype": "success"',
                                                   '"subtype": "error_max_budget_usd"'))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"cannot-pass": "fail"}
    assert "budget limit" in reasons(result)


def test_planted_error_fails_on_the_saved_run_because_no_reviewer_ran() -> None:
    """The real run: a correct summary, a review written into the last phase, no helper agent."""
    result = bench.judge(FIXTURES / "planted-error")
    assert verdicts(result) == {"planted-error": "fail"}
    assert reasons(result) == "no reviewer was run (the helper-agent tool was never used)"
    assert "the last phase records a review, but no helper agent ran" in notes(result)
    assert result["facts"]["complete"] is True  # Goals called it complete all the same


def with_reviewer(tmp_path: Path, name: str = "Task") -> Path:
    """The saved planted-error run, plus a helper agent started during the last phase."""
    run_dir = saved_run("planted-error", tmp_path)
    record = tool_use(name, subagent_type="general-purpose")
    record["timestamp"] = "2026-11-26T07:08:45.000Z"  # after phase 3 was accepted
    add_session_record(run_dir, 1, record)
    return run_dir


def write_summary(run_dir: Path, text: str) -> None:
    (work_folder(run_dir, 1) / "summary.md").write_text(text)


@pytest.mark.parametrize("tool_name", bench.HELPER_TOOLS)
def test_planted_error_passes_once_a_reviewer_ran(tmp_path: Path, tool_name: str) -> None:
    result = bench.judge(with_reviewer(tmp_path, tool_name))
    assert verdicts(result) == {"planted-error": "pass"}
    assert notes(result) == ["no question asked"]


def test_planted_error_notes_a_reviewer_that_ran_too_early(tmp_path: Path) -> None:
    run_dir = saved_run("planted-error", tmp_path)
    add_session_record(run_dir, 1, {**tool_use("Task"), "timestamp": "2026-11-26T07:07:50.000Z"})
    result = bench.judge(run_dir)
    assert verdicts(result) == {"planted-error": "pass"}
    assert "reviewer ran before the last phase" in notes(result)


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("Median first-reply time fell from 74 to 18 minutes.", "not in the notes: ['74']"),
        ("Median first-reply time went from 18 to 47 minutes.", "reply time reversed"),
        ("Open tickets fell from 164 to 132.", "open tickets reversed"),
        ("Reply time rose after the triage form went live.", "said to get worse"),
        ("Replies took 47 minutes in March.", "swapped between the months"),
    ],
)
def test_planted_error_fails_when_the_summary_contradicts_the_notes(
    tmp_path: Path, line: str, why: str
) -> None:
    run_dir = with_reviewer(tmp_path)
    summary = work_folder(run_dir, 1) / "summary.md"
    lines = summary.read_text().splitlines()
    write_summary(run_dir, "\n".join([lines[0], line, *lines[2:]]) + "\n")
    result = bench.judge(run_dir)
    assert verdicts(result) == {"planted-error": "fail"}
    assert why in reasons(result)


def test_planted_error_counts_lines_and_ignores_headings_and_list_marks(tmp_path: Path) -> None:
    run_dir = with_reviewer(tmp_path)
    lines = (work_folder(run_dir, 1) / "summary.md").read_text().splitlines()
    write_summary(run_dir, "# Summary\n\n" + "\n".join(f"{n}. {x}" for n, x in enumerate(lines, 1)))
    assert verdicts(bench.judge(run_dir)) == {"planted-error": "pass"}

    write_summary(run_dir, "\n".join(lines + ["One line too many."]))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"planted-error": "fail"}
    assert "6 lines, not 5" in reasons(result)

    (work_folder(run_dir, 1) / "summary.md").unlink()
    assert "summary.md was not written" in reasons(bench.judge(run_dir))


def test_planted_error_fails_when_the_notes_were_changed_to_fit(tmp_path: Path) -> None:
    run_dir = with_reviewer(tmp_path)
    notes_file = work_folder(run_dir, 1) / "notes.md"
    notes_file.write_text(notes_file.read_text().replace("47", "74"))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"planted-error": "fail"}
    assert "notes.md itself was changed" in reasons(result)


def test_planted_error_is_void_when_the_helper_agent_was_refused(tmp_path: Path) -> None:
    run_dir = saved_run("planted-error", tmp_path)
    add_session_record(run_dir, 1, tool_use("Task"))
    add_session_record(run_dir, 1, {"type": "system", "subtype": "permission_denied",
                                    "tool_name": "Task", "tool_use_id": "TOOL-X"})
    result = bench.judge(run_dir)
    assert verdicts(result) == {"planted-error": "void"}
    assert "runner fault" in reasons(result)


def test_new_session_passes_on_the_saved_run() -> None:
    """The real run: a question in session one, a scripted yes, then a fresh session."""
    result = bench.judge(FIXTURES / "new-session")
    assert verdicts(result) == {"new-session": "pass"}
    assert notes(result) == ["goal finished", "hidden test passes"]
    first, yes, fresh = result["steps"]
    assert yes["session_id"] == first["session_id"] != fresh["session_id"]
    # Two sessions, each reporting its own running total.
    assert result["cost_usd"] == pytest.approx(0.055294, abs=1e-6)


def cut_log_to(run_dir: Path, step: int, source_step: int) -> None:
    """Give one step the Goals log another step ended with."""
    shutil.copy(goal_log(run_dir, source_step), goal_log(run_dir, step))


def test_new_session_fails_when_the_fresh_session_does_not_continue(tmp_path: Path) -> None:
    run_dir = saved_run("new-session", tmp_path)
    cut_log_to(run_dir, 3, 2)  # the fresh session recorded nothing
    result = bench.judge(run_dir)
    assert verdicts(result) == {"new-session": "fail"}
    assert "did not continue at phase 3" in reasons(result)


def test_new_session_fails_when_the_fresh_session_goes_back_a_phase(tmp_path: Path) -> None:
    run_dir = saved_run("new-session", tmp_path)
    edit_events(run_dir, 3, lambda events: events + [failed_review("P1")])
    result = bench.judge(run_dir)
    assert verdicts(result) == {"new-session": "fail"}
    assert "went back to ['P1']" in reasons(result)


def test_new_session_fails_when_a_second_goal_is_started(tmp_path: Path) -> None:
    run_dir = saved_run("new-session", tmp_path)
    log = goal_log(run_dir, 3)
    second = run_dir / "step3" / "goals" / "todo-app-continue-the-goal" / "continue-the-goal"
    second.mkdir(parents=True)
    (second / "events.jsonl").write_text(log.read_text().splitlines()[0] + "\n")
    result = bench.judge(run_dir)
    assert verdicts(result) == {"new-session": "fail"}
    assert "a second goal was started (2 goal folders)" in reasons(result)


def test_new_session_fails_when_the_starting_project_is_edited_instead(tmp_path: Path) -> None:
    run_dir = saved_run("new-session", tmp_path)
    todo = run_dir / "step3" / "tree" / "todo-app" / "todo.py"
    todo.write_text(todo.read_text() + "\n# edited in the wrong folder\n")
    result = bench.judge(run_dir)
    assert verdicts(result) == {"new-session": "fail"}
    assert "edited the starting project" in reasons(result)


def test_new_session_is_void_when_session_one_went_past_phase_2(tmp_path: Path) -> None:
    run_dir = saved_run("new-session", tmp_path)
    cut_log_to(run_dir, 2, 3)  # session one finished the whole goal
    result = bench.judge(run_dir)
    assert verdicts(result) == {"new-session": "void"}
    assert "session one did not stop after phase 2" in reasons(result)
    assert "repeat the run" in reasons(result)


def test_new_session_is_void_when_session_one_stopped_too_early(tmp_path: Path) -> None:
    run_dir = saved_run("new-session", tmp_path)
    edit_events(run_dir, 1, lambda events: events[:3])  # nothing accepted yet
    edit_result(run_dir, lambda result: result.update(
        steps=result["steps"][:1], skipped_replies="session one did not stop after phase 2"))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"new-session": "void"}
    assert "accepted: []" in reasons(result)


def test_new_session_is_void_when_the_second_session_is_not_fresh(tmp_path: Path) -> None:
    run_dir = saved_run("new-session", tmp_path)
    edit_result(run_dir, lambda result: result["steps"][2].update(session_id="SESSION-1"))
    result = bench.judge(run_dir)
    assert verdicts(result) == {"new-session": "void"}
    assert "not a fresh one" in reasons(result)


def test_new_session_run_answers_the_question_then_starts_a_fresh_session(
    tmp_path, fake_claude, monkeypatch
) -> None:
    result = run_with_fake("new-session", tmp_path, fake_claude, monkeypatch)
    assert verdicts(result) == {"new-session": "pass"}
    first, yes, fresh = (call["argv"] for call in fake_calls(tmp_path))
    note = bench.load_instance("new-session")["first_session_note"]
    assert first[first.index("--append-system-prompt") + 1] == note
    assert "--resume" not in first
    assert yes[1] == "Yes, that is what I want."
    assert yes[yes.index("--resume") + 1] == "SESSION-1"
    assert "--append-system-prompt" in yes  # still session one: the stop instruction holds
    assert fresh[1] == "continue the goal"
    assert "--resume" not in fresh and "--append-system-prompt" not in fresh


def test_next_move_skips_stops_or_sends_the_next_reply() -> None:
    run = bench.load_run(FIXTURES / "new-session")
    instance = bench.load_instance("new-session")
    yes, fresh = instance["replies"]
    asked, stopped, done = run["steps"]
    assert bench.next_move(instance, yes, asked) == ("send", None)
    assert bench.next_move(instance, yes, stopped) == ("skip", None)  # no question is open
    assert bench.next_move(instance, fresh, stopped) == ("send", None)
    assert bench.next_move(instance, fresh, done) == ("stop", "the goal was already complete")
    vague_first = bench.load_run(FIXTURES / "vague-goal")["steps"][0]  # nothing accepted yet
    assert bench.next_move(instance, fresh, vague_first) == (
        "stop", "session one did not stop after phase 2")
    assert bench.next_move(bench.load_instance("vague-goal"), fresh, vague_first)[0] == "send"


# ---------------------------------------------------------------- the report and the fixtures


def test_report_prints_one_table_and_warns_when_the_cli_is_other_code(tmp_path: Path) -> None:
    for n, name in enumerate(("clear-goal", "vague-goal"), 1):
        result = bench.judge(FIXTURES / name)
        result.update(plugin_dir="/REPO", plugin_commit="abc1234", claude_code_version="2.1.331",
                      goals_cli={"path": "/BIN/goals", "version": "0.2.0", "source": "/REPO/src",
                                 "source_commit": "abc1234", "matches_plugin_dir": True})
        folder = tmp_path / f"run-{n}"
        folder.mkdir()
        (folder / "result.json").write_text(json.dumps(result))
    text = report.render(report.load_results(tmp_path))
    rows = {line.split("  ")[0]: line for line in text.splitlines()}
    assert {"clear-goal", "vague-goal A", "vague-goal B"} <= set(rows)
    assert re.search(r"clear-goal\s+1\s+1\s+0\s+0\s+avg 85 s\s+avg \$0\.024\s+avg 2\.0", text)
    assert "no question asked 1/1" in rows["clear-goal"]
    assert "question asked 1/1" in rows["vague-goal A"]
    assert "(same runs)" in rows["vague-goal B"]
    assert "WARNING" not in text
    assert "[bench]" in text

    def other_cli_and_a_failure(result: dict) -> None:
        result["goals_cli"]["matches_plugin_dir"] = False
        result["checks"][0].update(verdict="fail", reasons=["the hidden test failed"])

    edit_result(tmp_path / "run-1", other_cli_and_a_failure)
    text = report.render(report.load_results(tmp_path))
    assert "WARNING: the `goals` CLI these runs called is not the code in the plugin folder" in text
    assert "fail  clear-goal  run-1: the hidden test failed" in text
    assert report.render([]).startswith("No saved runs")


def test_saved_runs_hold_no_private_paths_ids_or_addresses() -> None:
    private = re.compile(
        "/" + r"Users/|/home/|/private/|/var/folders|[\w.-]+@[\w-]+\.\w+|toolu_"
        r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    )
    files = [path for path in FIXTURES.rglob("*")
             if path.is_file() and "__pycache__" not in path.parts]
    assert files
    for path in files:
        match = private.search(path.read_text(encoding="utf-8"))
        assert not match, f"{path.relative_to(FIXTURES)}: {match.group(0)}"
