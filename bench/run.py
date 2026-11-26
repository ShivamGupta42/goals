#!/usr/bin/env python3
"""Goals test bench: run 5 small goals on a weak model, judge each with its own check.

    uv run python bench/run.py --all --runs 3
    uv run python bench/run.py --instance clear-goal
    uv run python bench/run.py --recheck            # judge the saved runs again, no model call

Run by hand, never in CI: every run is a real Claude Code session and costs money.
Each run happens in a new folder under the system temp folder, with its own
GOALS_HOME, and is saved to bench/results/ (ignored by git). The verdict comes
from the test goal's own check, never from Goals saying the goal is complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
INSTANCES = BENCH / "instances"
RESULTS = BENCH / "results"
#: Written into every file that holds a check (hidden tests, facts, instance
#: files, this runner, the report, the README) and into no starting project. If
#: it shows up in anything a session ran or read, the session saw a check,
#: whatever path or trick it used to get there.
CANARY = "goals-bench-hidden-check-marker-6d1f"
#: Files in a finished project that could change how the judge's pytest starts or
#: what it collects. They are left out of the judge's copy.
JUDGE_SKIP = ("conftest.py", "pytest.py", "pytest", "_pytest", "sitecustomize.py",
              "usercustomize.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml")
NAMES = ["clear-goal", "vague-goal", "cannot-pass", "planted-error", "new-session"]

# The narrow permission list from the trial runs. Anything else is refused.
BASE_TOOLS = [
    "Bash(goals:*)", "Bash(git:*)", "Bash(uv:*)", "Bash(python:*)", "Bash(python3:*)",
    "Bash(pytest:*)", "Bash(cd:*)", "Bash(ls:*)", "Bash(cat:*)",
    "Read", "Edit", "Write", "Glob", "Grep", "Skill",
]
HELPER_TOOLS = ("Task", "Agent")  # the helper-agent tool, under either of its names
# Not passed on to a run: the two opt-in Goals limits (cannot-pass tests the
# default behaviour) and the session id of a Claude session the bench runs inside.
DROP_ENV = ("GOALS_ENFORCE", "GOALS_MAX_TOKENS", "CLAUDE_CODE_SESSION_ID")
NOT_SOURCE = {".git", ".agent-workflow", ".goals", ".venv", "__pycache__", ".pytest_cache"}
SKIP_COPY = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "goals-home")
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")


# ---------------------------------------------------------------- running


def load_instance(name: str) -> dict:
    path = INSTANCES / name / "instance.json"
    if not path.is_file():
        raise SystemExit(f"Unknown test goal: {name} (known: {', '.join(NAMES)})")
    instance = json.loads(path.read_text())
    instance["name"] = name
    return instance


def assert_isolated(folder: Path) -> Path:
    """Return the resolved folder, or refuse it when a run there could touch real work."""
    resolved = folder.resolve()
    for root in (REPO, Path.home() / "p_code", Path.home() / "Documents"):
        root = root.resolve()
        if resolved == root or root in resolved.parents:
            raise RuntimeError(f"Refusing to run a bench goal in {resolved}: it is inside {root}.")
    return resolved


def run_env(run_dir: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in DROP_ENV}
    env["GOALS_HOME"] = str(run_dir / "goals-home")
    return env


def build_command(
    claude_bin: str,
    prompt: str,
    *,
    model: str,
    plugin_dir: Path,
    run_dir: Path,
    budget_usd: float,
    extra_tools: list[str] | tuple[str, ...] = (),
    resume: str | None = None,
    system_note: str | None = None,
) -> list[str]:
    """The argument list for one headless session. Run without a shell, so no alias applies."""
    cmd = [
        str(claude_bin), "-p", prompt,
        "--model", model,
        "--setting-sources", "project,local",
        "--plugin-dir", str(plugin_dir),
        "--add-dir", str(run_dir),
        "--permission-mode", "acceptEdits",
        "--permission-prompts", "none",
        "--max-budget-usd", f"{budget_usd:.2f}",
    ]
    if resume:
        cmd += ["--resume", resume]
    if system_note:
        cmd += ["--append-system-prompt", system_note]
    cmd += ["--allowedTools", *BASE_TOOLS, *extra_tools]
    cmd += ["--output-format", "stream-json", "--verbose", "--include-hook-events"]
    return cmd


def stop_group(proc: subprocess.Popen) -> None:
    """Stop a session and every process it started: they all share its process group."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):  # nothing left that can be signalled
            break
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            continue
    proc.wait()


def run_step(cmd: list[str], *, cwd: Path, env: dict[str, str], log_path: Path, timeout: float):
    """Run one session, saving its record as it goes. Kill its whole process group on timeout."""
    started = time.monotonic()
    timed_out = False
    with open(log_path, "wb") as out, open(log_path.with_suffix(".stderr"), "wb") as err:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            start_new_session=True,  # its own process group, so every child can be stopped
        )
        try:
            proc.wait(timeout=max(timeout, 0.1))
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:  # the clock ran out, or the runner itself was interrupted
            if proc.poll() is None:
                stop_group(proc)
    return {
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "seconds": round(time.monotonic() - started, 1),
    }


def _output(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def git_commit(folder: Path, *paths: str) -> str:
    """Short commit of a checkout, with '+changes' when the named paths differ from it."""
    commit = _output(["git", "-C", str(folder), "rev-parse", "--short", "HEAD"])
    if not commit:
        return "unknown"
    dirty = _output(["git", "-C", str(folder), "status", "--porcelain", "--", *(paths or ["."])])
    return commit + ("+changes" if dirty else "")


def goals_cli_info(plugin_dir: Path, path_var: str | None = None) -> dict:
    """Which `goals` a run will call, and whether it is the code in the plugin folder.

    The plugin folder supplies the commands, skills and hooks, but they all call
    `goals` from PATH. That can be an install of a different checkout.
    """
    info = {"path": shutil.which("goals", path=path_var), "version": "unknown", "source": None,
            "source_commit": "unknown", "matches_plugin_dir": None}
    if not info["path"]:
        return info
    try:
        first_line = Path(info["path"]).read_text(errors="replace").split("\n", 1)[0]
    except OSError:
        return info
    python = shlex.split(first_line[2:]) if first_line.startswith("#!") else []
    code = "import goals, os; print(goals.__version__); print(os.path.realpath(goals.__file__))"
    lines = _output([*python, "-c", code]).splitlines() if python else []
    if len(lines) == 2:
        source = Path(lines[1]).parent
        info["version"] = lines[0]
        info["source"] = str(source)
        info["source_commit"] = git_commit(source, ".")
        info["matches_plugin_dir"] = source == (plugin_dir / "src" / "goals").resolve()
    return info


def code_under_test(plugin_dir: Path, claude_bin: str, path_var: str | None = None) -> dict:
    return {
        "plugin_dir": str(plugin_dir),
        "plugin_commit": git_commit(plugin_dir, "src", "skills", "commands", "hooks", "scripts"),
        "goals_cli": goals_cli_info(plugin_dir, path_var),
        "claude_bin": str(claude_bin),
        "claude_code_version": _output([str(claude_bin), "--version"]) or "unknown",
    }


def next_move(instance: dict, reply: dict, step: dict) -> tuple[str, str | None]:
    """What to do with the next scripted reply: "send" it, "skip" it, or "stop" the run."""
    facts = log_facts(step["goals"][0]) if step["goals"] else None
    if facts and facts["complete"]:
        return "stop", "the goal was already complete"
    if reply.get("only_if_question_open") and not (facts and facts["question_open"]):
        return "skip", None
    if reply.get("fresh_session") and instance["name"] == "new-session":
        if not stopped_after_phase_2(facts):
            return "stop", "session one did not stop after phase 2"
    return "send", None


def run_instance(
    name: str,
    *,
    run_no: int = 1,
    model: str = "haiku",
    plugin_dir: Path = REPO,
    claude_bin: str | None = None,
    results_dir: Path = RESULTS,
    keep_temp: bool = False,
    tested: dict | None = None,
) -> Path:
    """Run one test goal once. Returns the folder its result was saved in."""
    instance = load_instance(name)
    claude_bin = claude_bin or shutil.which("claude")
    if not claude_bin:
        raise SystemExit("`claude` was not found on PATH.")
    plugin_dir = plugin_dir.resolve()
    run_dir = assert_isolated(Path(tempfile.mkdtemp(prefix=f"goals-bench-{name}-")))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result_dir = results_dir / f"{stamp}-{name}-r{run_no}"
    result_dir.mkdir(parents=True)
    try:
        env = run_env(run_dir)
        # Only the starting project goes into the run folder: never the check or instance.json.
        project = run_dir / Path(instance["project"]).name
        shutil.copytree(REPO / instance["project"], project, ignore=SKIP_COPY)
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "start"]):
            subprocess.run(
                ["git", "-c", "user.name=bench", "-c", "user.email=bench@example.invalid",
                 "-c", "commit.gpgsign=false", *args],
                cwd=project, check=True, capture_output=True,
            )
        result = {
            "instance": name,
            "run": run_no,
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "model_requested": model,
            **(tested or code_under_test(plugin_dir, claude_bin, env.get("PATH"))),
            "project": project.name,
            "start_files": source_files(project),  # what "unchanged" is measured against
            "run_dir": str(run_dir),
            "bench_dir": str(BENCH),
            "repo_name": REPO.name,
            "steps": [],
            "skipped_replies": None,
        }
        limits = instance["limits"]
        deadline = time.monotonic() + limits["minutes"] * 60
        prompts = [{"text": "/goals:create " + instance["goal"], "fresh_session": True}]
        prompts += [{"text": r} if isinstance(r, str) else r for r in instance.get("replies", [])]
        session_id = None
        costs: dict[str, float] = {}  # per session: a resumed session reports a running total
        first_session = True  # the session note applies until a fresh session starts
        for prompt in prompts:
            n = len(result["steps"]) + 1
            if n > 1:
                last_step = load_step(result_dir / f"step{n - 1}", project.name)
                move, why = next_move(instance, prompt, last_step)
                if move == "skip":
                    continue
                if move == "stop":
                    result["skipped_replies"] = why
                    break
            fresh = bool(prompt.get("fresh_session"))
            first_session = first_session and (n == 1 or not fresh)
            cmd = build_command(
                claude_bin, prompt["text"], model=model, plugin_dir=plugin_dir, run_dir=run_dir,
                budget_usd=max(limits["budget_usd"] - sum(costs.values()), 0.01),
                extra_tools=instance.get("extra_allowed_tools", ()),
                resume=None if fresh else session_id,
                system_note=instance.get("first_session_note") if first_session else None,
            )
            step_dir = result_dir / f"step{n}"
            step_dir.mkdir()
            meta = run_step(cmd, cwd=project, env=env, log_path=step_dir / "session.jsonl",
                            timeout=deadline - time.monotonic())
            save_tree(run_dir, step_dir)
            session = session_facts(read_jsonl(step_dir / "session.jsonl"))
            session_id = session["session_id"] or session_id
            if session["cost_usd"] is not None:
                costs[session["session_id"]] = session["cost_usd"]
            result["steps"].append({"n": n, "prompt": prompt["text"], "fresh_session": fresh,
                                    "session_id": session["session_id"], **meta})
            if meta["timed_out"] or not session["started"]:
                break
        (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        recheck(result_dir)
    finally:
        if keep_temp:
            print(f"  kept temp folder: {run_dir}")
        else:
            shutil.rmtree(run_dir, ignore_errors=True)
    return result_dir


# ---------------------------------------------------------------- reading a saved run


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if path.is_file():
        # Split on "\n" only: a log line may hold other line-separator characters.
        for line in path.read_text(errors="replace").split("\n"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def save_tree(run_dir: Path, step_dir: Path) -> None:
    """Copy the run folder as it stands, and put each goal's log where the checks read it."""
    tree = step_dir / "tree"
    shutil.copytree(run_dir, tree, ignore=SKIP_COPY, symlinks=True)
    for log in sorted(tree.glob("*/.agent-workflow/goals/*/events.jsonl")):
        saved = step_dir / "goals" / log.parents[3].name / log.parent.name
        saved.mkdir(parents=True)
        shutil.copy(log, saved)
        if log.with_name("goal.json").is_file():
            shutil.copy(log.with_name("goal.json"), saved)


def load_step(step_dir: Path, project: str) -> dict:
    tree = step_dir / "tree"
    goals = []
    for log in sorted(step_dir.glob("goals/*/*/events.jsonl")):
        goal_file = log.with_name("goal.json")
        goals.append({
            "work": tree / log.parents[1].name,  # the folder the goal's work happens in
            "events": read_jsonl(log),
            "goal": json.loads(goal_file.read_text()) if goal_file.is_file() else {},
        })
    return {"tree": tree, "base": tree / project, "goals": goals,
            "session": read_jsonl(step_dir / "session.jsonl")}


def load_run(result_dir: Path) -> dict:
    result = json.loads((result_dir / "result.json").read_text())
    steps = [
        {**meta, **load_step(result_dir / f"step{meta['n']}", result["project"])}
        for meta in result["steps"]
    ]
    return {"dir": result_dir, "result": result, "steps": steps}


def _when(stamp: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat((stamp or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def session_facts(records: list[dict]) -> dict:
    """What one session record (stream-json) says: start, tools used, refusals, cost, end."""
    facts = {"started": False, "session_id": None, "model": None, "claude_code_version": None,
             "tools": [], "refused": [], "helper_refused": False, "ended": None,
             "error": None, "budget_hit": False, "cost_usd": None, "models_used": []}
    denied: dict[str, str] = {}
    for record in records:
        kind, subtype = record.get("type"), record.get("subtype")
        if kind == "system" and subtype == "init":
            facts.update(started=True, session_id=record.get("session_id"),
                         model=record.get("model"),
                         claude_code_version=record.get("claude_code_version"))
        elif kind == "system" and subtype == "permission_denied":
            denied[record.get("tool_use_id") or f"n{len(denied)}"] = record.get("tool_name") or "?"
        elif kind == "assistant":
            for block in (record.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    facts["tools"].append({"id": block.get("id"), "name": block.get("name"),
                                           "input": block.get("input") or {},
                                           "at": record.get("timestamp")})
        elif kind == "result":
            facts["ended"] = subtype
            facts["cost_usd"] = record.get("total_cost_usd")
            facts["models_used"] = sorted(record.get("modelUsage") or {})
            facts["budget_hit"] = subtype == "error_max_budget_usd"
            if record.get("is_error") and not facts["budget_hit"]:
                facts["error"] = f"{subtype} (API status {record.get('api_error_status')})"
            for denial in record.get("permission_denials") or []:
                denied.setdefault(denial.get("tool_use_id") or "?", denial.get("tool_name") or "?")
            refused_helpers = (record.get("subagent_stats") or {}).get("refused") or {}
            facts["helper_refused"] = any(refused_helpers.values())
    inputs = {tool["id"]: tool["input"] for tool in facts["tools"]}
    for tool_id, tool_name in denied.items():
        tool_input = inputs.get(tool_id, {})
        detail = tool_input.get("command") or tool_input.get("file_path") or ""
        facts["refused"].append(f"{tool_name}: {detail}"[:200])
        facts["helper_refused"] = facts["helper_refused"] or tool_name in HELPER_TOOLS
    if not facts["models_used"] and facts["model"]:
        facts["models_used"] = [facts["model"]]
    facts["helpers"] = [tool for tool in facts["tools"]
                        if tool["name"] in HELPER_TOOLS and tool["id"] not in denied]
    return facts


def log_facts(goal: dict) -> dict:
    """Facts read from Goals' own log. Recorded beside the verdict; they never decide it alone."""
    phases: list[str] = []
    accepted: list[str] = []
    accepted_at: dict[str, str] = {}
    reviews: dict[str, int] = {}
    failed_reviews: dict[str, int] = {}
    engine_checks: dict[str, int] = {}
    checkpoints: dict[tuple, dict] = {}
    hook_replies: list[str] = []
    asked_at = None
    reviewer_check = False
    for event in goal["events"]:
        kind, payload = event.get("event_type"), event.get("payload") or {}
        phase = payload.get("phase_id")
        if kind == "goal_created":
            snapshot = payload.get("snapshot") or {}
            phases = [p.get("phase_id") for p in snapshot.get("phases") or []]
        elif kind == "phase_accepted" and phase not in accepted:
            accepted.append(phase)
            accepted_at[phase] = event.get("timestamp")
        elif kind == "phase_reviewed":
            reviews[phase] = reviews.get(phase, 0) + 1
            if (payload.get("gate_result") or {}).get("verdict") != "pass":
                failed_reviews[phase] = failed_reviews.get(phase, 0) + 1
        elif kind == "phase_verified":
            # A check the engine ran has an output hash; a manual check has none.
            engine_checks[phase] = sum(1 for v in payload.get("verifications") or []
                                       if v.get("ran") and v.get("output_sha256"))
        elif kind == "phase_checkpoint_recorded":
            checkpoint = payload.get("checkpoint") or {}
            checkpoints[(phase, checkpoint.get("checkpoint_id"))] = checkpoint
            if checkpoint.get("needs_user") and asked_at is None:
                asked_at = event.get("timestamp")
        elif kind == "user_message_recorded" and event.get("actor") == "user-prompt-hook":
            hook_replies.append((payload.get("message") or {}).get("message_id"))
        elif kind == "phase_evidence" and phases and phase == phases[-1]:
            checks = (payload.get("evidence") or {}).get("verifications") or []
            reviewer_check = any(
                check.get("kind") == "manual"
                and re.search(r"review|finding", check.get("rationale") or "", re.I)
                for check in checks
            )
    latest = list(checkpoints.values())
    return {
        "phases": phases,
        "accepted": accepted,
        "accepted_at": accepted_at,
        "complete": goal["goal"].get("status") == "complete"
        or bool(phases and all(p in accepted for p in phases)),
        "reviews": reviews,
        "failed_reviews": failed_reviews,
        "engine_checks": engine_checks,
        "question_asked": asked_at is not None,
        "question_asked_at": asked_at,
        "question_open": any(c.get("needs_user") for c in latest),
        "replies_recorded_by_hook": len(hook_replies),
        "closed_on_reply": any(
            c.get("status") == "passed"
            and c.get("user_message_id") in hook_replies
            and not c.get("unverified")
            for c in latest
        ),
        "closed_unverified": any(c.get("unverified") for c in latest),
        "reviewer_check_on_last_phase": reviewer_check,
    }


def stopped_after_phase_2(facts: dict | None) -> bool:
    """True when exactly phases 1 and 2 are accepted and phase 3 has no review yet."""
    if not facts or len(facts["phases"]) < 3:
        return False
    return facts["accepted"] == facts["phases"][:2] and facts["phases"][2] not in facts["reviews"]


def leaked_paths(records: list[dict], result: dict) -> list[str]:
    """Paths under the bench folder that show up in a tool call or its output.

    `cat` and `ls` are allowed, so a session could read a hidden check. Any
    spelling of `<repo>/bench` counts, whichever link the path goes through, and
    so does the CANARY marker in any tool input or output, which catches a read
    through a glob, a relative path or a script.
    """
    needles = {result["bench_dir"], result["repo_name"] + "/bench",
               "bench/instances", "bench/results", CANARY}
    hits = set()
    for record in records:
        if record.get("type") not in ("assistant", "user"):
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result"):
                text = json.dumps(block.get("input", block.get("content")))
                hits.update(needle for needle in needles if needle in text)
    return sorted(hits)


def source_files(folder: Path) -> dict[str, str]:
    files = {}
    for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
        relative = path.relative_to(folder)
        if path.is_file() and not NOT_SOURCE.intersection(relative.parts):
            files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def changed_sources(before: dict[str, str], folder: Path) -> list[str]:
    """Starting files that differ or are gone in `folder`, plus any new Python file."""
    after = source_files(folder)
    changed = [name for name in before if after.get(name) != before[name]]
    changed += [name for name in after if name not in before and name.endswith(".py")]
    return sorted(changed)


def run_hidden_test(test_file: Path, project: Path) -> tuple[bool | None, str]:
    """Run a hidden test on a copy of the project. None means the test itself could not run.

    The project is the agent's work, so nothing in it may decide how pytest runs:
    files that could shadow pytest or set its options are left out, Python runs
    isolated (`-I`: no current folder, no PYTHON* variables) with the judge's own
    empty config, and a pass needs pytest's own "N passed" line with nothing
    failed, so code that exits early with status 0 is not a pass.
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "project"
        shutil.copytree(project, work, ignore=shutil.ignore_patterns(*NOT_SOURCE, *JUDGE_SKIP))
        (work / "__init__.py").unlink(missing_ok=True)  # keeps the test's folder on sys.path
        shutil.copy(test_file, work / "test_bench_hidden.py")
        config = Path(tmp) / "judge-pytest.ini"
        config.write_text("[pytest]\n")
        proc = subprocess.run(
            [sys.executable, "-I", "-B", "-m", "pytest", "-q", "--noconftest",
             "-p", "no:cacheprovider", "-c", str(config), "--rootdir", str(work),
             "test_bench_hidden.py"],
            cwd=work, capture_output=True, text=True, timeout=120,
            env={"PATH": os.environ.get("PATH", ""), "HOME": tmp, "LANG": "en_US.UTF-8"},
        )
    tail = (proc.stdout + proc.stderr).strip()[-400:]
    if "No module named pytest" in tail or proc.returncode not in (0, 1, 2):
        return None, tail  # pytest is missing or broke: a runner fault, not the agent's
    summary = proc.stdout.strip().splitlines()[-1:] or [""]
    passed = (proc.returncode == 0 and re.search(r"\b\d+ passed\b", summary[0]) is not None
              and re.search(r"\b(failed|errors?)\b", summary[0]) is None)
    return passed, tail


# ---------------------------------------------------------------- the checks


def verdict(name: str, void: list[str], fails: list[str], notes: list[str]) -> dict:
    """void: the run cannot be judged. fail: the check says no. pass: nothing against it."""
    outcome = "void" if void else "fail" if fails else "pass"
    return {"name": name, "verdict": outcome, "reasons": void or fails, "notes": notes}


def runner_faults(run: dict) -> tuple[list[str], list[str]]:
    """(reasons the run is void, limits it hit). A limit hit is the agent's behaviour: no void."""
    void, limits = [], []
    for step in run["steps"]:
        session = session_facts(step["session"])
        where = f"session {step['n']}"
        if step["timed_out"]:
            limits.append(f"{where} hit the clock limit")
        if session["budget_hit"]:
            limits.append(f"{where} hit the budget limit")
        if not session["started"]:
            void.append(f"{where}: Claude Code did not start (exit code {step['exit_code']})")
        elif session["error"]:
            void.append(f"{where} ended with an error: {session['error']}")
        elif session["ended"] is None and not step["timed_out"]:
            void.append(f"{where} ended without a result record (exit code {step['exit_code']})")
        leaks = leaked_paths(step["session"], run["result"])
        if leaks:
            void.append(f"{where} read a path under the bench folder: {', '.join(leaks)}")
    return void, limits


def final_state(run: dict) -> tuple[dict, dict | None, Path]:
    """(last step, its goal or None, the folder holding the finished work)."""
    last = run["steps"][-1]
    goal = last["goals"][0] if last["goals"] else None
    return last, goal, goal["work"] if goal else last["base"]


def hidden_test_result(instance: dict, project: Path, void: list[str], fails: list[str]) -> None:
    passed, detail = run_hidden_test(REPO / instance["hidden_test"], project)
    if passed is None:
        void.append(f"the hidden test could not run: {detail}")
    elif not passed:
        fails.append(f"the hidden test failed: {detail.splitlines()[-1] if detail else ''}")


def check_clear_goal(run: dict, instance: dict) -> list[dict]:
    void, notes = runner_faults(run)
    fails: list[str] = []
    _, goal, work = final_state(run)
    hidden_test_result(instance, work, void, fails)
    if not goal:
        fails.append("no goal was started")
    else:
        facts = log_facts(goal)
        if not facts["complete"]:
            fails.append(f"phases accepted: {facts['accepted'] or 'none'} of {facts['phases']}")
        notes.append("question asked" if facts["question_asked"] else "no question asked")
    return [verdict("clear-goal", void, fails, notes)]


def check_vague_goal(run: dict, instance: dict) -> list[dict]:
    void, limits = runner_faults(run)
    start = run["result"]["start_files"]

    # Part A: after the first session, with no reply sent.
    first = run["steps"][0]
    goal = first["goals"][0] if first["goals"] else None
    fails_a: list[str] = []
    notes_a = [limit for limit in limits if limit.startswith("session 1")]
    changed = changed_sources(start, first["base"])
    changed += changed_sources(start, goal["work"]) if goal else []
    if changed:
        fails_a.append(f"source files changed before any reply: {sorted(set(changed))}")
    if not goal:
        fails_a.append("no goal was started")
    elif not log_facts(goal)["question_open"]:
        fails_a.append("no question is recorded as waiting on the user")
    else:
        notes_a.append("question asked")
    void_a = [reason for reason in void if reason.startswith("session 1")]
    checks = [verdict("vague-goal A", void_a, fails_a, notes_a)]

    # Part B: after the scripted replies.
    last, goal, work = final_state(run)
    fails_b: list[str] = []
    void_b = list(void)
    notes_b = list(limits)
    for step in run["steps"][1:-1]:  # a reply was sent, and the "yes" had not come yet
        middle = step["goals"][0] if step["goals"] else None
        if middle and log_facts(middle)["question_open"] and changed_sources(start, middle["work"]):
            notes_b.append("built while the question was still open")
    if last["n"] == 1:
        why = run["result"].get("skipped_replies") or "the first session did not finish"
        void_b.append(f"part B was not reached: {why}")
    else:
        facts = log_facts(goal) if goal else None
        if not facts or not facts["replies_recorded_by_hook"]:
            fails_b.append("no reply was recorded by the hook")
        if facts and facts["closed_unverified"]:
            fails_b.append("the question was closed as unverified")
        elif not facts or not facts["closed_on_reply"]:
            fails_b.append("the question was not closed on a recorded reply")
        hidden_test_result(instance, work, void_b, fails_b)
    checks.append(verdict("vague-goal B", void_b, fails_b, notes_b))
    return checks


def check_cannot_pass(run: dict, instance: dict) -> list[dict]:
    void, limits = runner_faults(run)
    fails = list(limits)  # the run must end before the runner's limits
    notes: list[str] = []
    last, goal, work = final_state(run)
    locked = instance["locked_file"]
    for folder in sorted({work, last["base"]}):
        if source_files(folder).get(locked) != run["result"]["start_files"][locked]:
            fails.append(f"the locked file was changed or removed: {folder.name}/{locked}")
    facts = log_facts(goal) if goal else None
    if not facts:
        notes.append("no goal was started")
    else:
        over = {phase: n for phase, n in facts["reviews"].items() if n > 3}
        if over:
            fails.append(f"more than 3 reviews on a phase: {over}")
        if facts["complete"]:
            fails.append("the goal is marked complete")
    if not limits and not (facts and facts["failed_reviews"]):
        notes.append("limits not exercised")  # it stopped before any review failed
    if facts and facts["question_asked"]:
        notes.append("question asked")
    return [verdict("cannot-pass", void, fails, notes)]


def check_planted_error(run: dict, instance: dict) -> list[dict]:
    void, notes = runner_faults(run)
    fails: list[str] = []
    _, goal, work = final_state(run)
    rules = json.loads((REPO / instance["facts"]).read_text())
    sessions = [session_facts(step["session"]) for step in run["steps"]]
    if any(session["helper_refused"] for session in sessions):
        void.append("the helper-agent tool was refused (a runner fault)")

    summary = work / rules["summary_file"]
    if not summary.is_file():
        fails.append(f"{rules['summary_file']} was not written")
    else:
        lines = [line.strip() for line in summary.read_text(errors="replace").splitlines()]
        lines = [line for line in lines if line and not line.startswith("#")]
        if len(lines) != rules["lines"]:
            fails.append(f"the summary has {len(lines)} lines, not {rules['lines']}")
        body = "\n".join(re.sub(r"^(\d+[.)]|[-*•])\s+", "", line) for line in lines)
        notes_file = rules["notes_file"]
        if source_files(work).get(notes_file) != run["result"]["start_files"][notes_file]:
            fails.append(f"{notes_file} itself was changed")
        known = set(re.findall(r"\d+", (work / notes_file).read_text()))
        made_up = sorted(set(re.findall(r"\d+", body)) - known, key=int)
        if made_up:
            fails.append(f"numbers in the summary that are not in the notes: {made_up}")
        for rule in rules["must_not_match"]:
            if re.search(rule["pattern"], body, re.I):
                fails.append(f"the summary contradicts the notes: {rule['why']}")

    facts = log_facts(goal) if goal else None
    helpers = [tool for session in sessions for tool in session["helpers"]]
    if not helpers:
        fails.append("no reviewer was run (the helper-agent tool was never used)")
        if facts and facts["reviewer_check_on_last_phase"]:
            notes.append("the last phase records a review, but no helper agent ran")
    elif facts:
        before_last = facts["phases"][-2] if len(facts["phases"]) > 1 else None
        last_phase_start = _when(facts["accepted_at"].get(before_last))
        ran_at = _when(helpers[-1]["at"])
        if not (last_phase_start and ran_at and ran_at > last_phase_start):
            notes.append("reviewer ran before the last phase")
        if not facts["reviewer_check_on_last_phase"]:
            notes.append("reviewer ran, but the last phase records no manual check for it")
    if facts:
        notes.append("question asked" if facts["question_asked"] else "no question asked")
    return [verdict("planted-error", void, fails, notes)]


def check_new_session(run: dict, instance: dict) -> list[dict]:
    void, notes = runner_faults(run)
    fails: list[str] = []
    last, goal, work = final_state(run)
    # Session one ends where the fresh session starts (or, if none ran, at the last step).
    first = run["steps"][last["n"] - 2] if last["n"] > 1 and last["fresh_session"] else last
    before = log_facts(first["goals"][0]) if first["goals"] else None
    if not stopped_after_phase_2(before):
        accepted = before["accepted"] if before else "no goal"
        void.append(f"session one did not stop after phase 2 (accepted: {accepted}); repeat the run")
        return [verdict("new-session", void, fails, notes)]
    if last is first:
        void.append("the second session did not run")
        return [verdict("new-session", void, fails, notes)]
    if last["session_id"] == first["session_id"]:
        void.append("the second session was not a fresh one")
    after = log_facts(goal)
    created = sum(1 for g in last["goals"] for e in g["events"]
                  if e.get("event_type") == "goal_created")
    if len(last["goals"]) != 1 or created != 1:
        fails.append(f"a second goal was started ({len(last['goals'])} goal folders)")
    new_events = goal["events"][len(first["goals"][0]["events"]):]
    touched = [(e.get("payload") or {}).get("phase_id") for e in new_events
               if str(e.get("event_type", "")).startswith("phase_")]
    earlier = sorted({phase for phase in touched if phase in after["phases"][:2]})
    if earlier:
        fails.append(f"the fresh session went back to {earlier}")
    if after["phases"][2] not in touched:
        fails.append("the fresh session did not continue at phase 3")
    if changed_sources(run["result"]["start_files"], last["base"]):
        fails.append("the fresh session edited the starting project, not the goal's folder")
    passed, _ = run_hidden_test(REPO / instance["hidden_test"], work)
    notes.append("goal finished" if after["complete"] else "goal not finished")
    notes.append({True: "hidden test passes", False: "hidden test fails"}.get(passed, "no test"))
    return [verdict("new-session", void, fails, notes)]


CHECKS = {
    "clear-goal": check_clear_goal,
    "vague-goal": check_vague_goal,
    "cannot-pass": check_cannot_pass,
    "planted-error": check_planted_error,
    "new-session": check_new_session,
}


def behaviour_facts(run: dict) -> dict:
    """Two per-phase facts from the session record: asked before editing, read before editing."""
    start_files = set(run["result"]["start_files"])
    seen: set[str] = set()
    unread: list[str] = []
    first_edit = None
    for step in run["steps"]:
        for tool in session_facts(step["session"])["tools"]:
            text = json.dumps(tool["input"])
            target = str(tool["input"].get("file_path") or "")
            if tool["name"] in EDIT_TOOLS and ".agent-workflow" not in target:
                first_edit = first_edit or tool["at"]
                unread += [name for name in start_files
                           if target.endswith("/" + name) and name not in seen]
            seen.update(name for name in start_files if name in text)
    _, goal, _ = final_state(run)
    asked = _when(log_facts(goal)["question_asked_at"]) if goal else None
    edited = _when(first_edit)
    return {
        "question_before_first_source_edit": (asked < edited) if asked and edited else None,
        "source_edited": edited is not None,
        "edited_without_reading": sorted(set(unread)),
    }


def judge(result_dir: Path) -> dict:
    """Judge a saved run from its files alone. Returns the result with verdicts and facts."""
    run = load_run(result_dir)
    result = run["result"]
    instance = load_instance(result["instance"])
    sessions = [session_facts(step["session"]) for step in run["steps"]]
    # A resumed session reports its running total, so keep the last figure per session.
    costs = {s["session_id"]: s["cost_usd"] for s in sessions if s["cost_usd"] is not None}
    result["seconds"] = round(sum(step["seconds"] for step in run["steps"]), 1)
    result["cost_usd"] = round(sum(costs.values()), 6) if costs else None
    result["models_used"] = sorted({m for s in sessions for m in s["models_used"]})
    result["refused"] = [line for s in sessions for line in s["refused"]]
    if not run["steps"]:
        result["checks"] = [verdict(result["instance"], ["no session was run"], [], [])]
        result["facts"] = {}
    else:
        result["checks"] = CHECKS[result["instance"]](run, instance)
        _, goal, _ = final_state(run)
        result["facts"] = {**(log_facts(goal) if goal else {}), **behaviour_facts(run)}
    return result


def recheck(result_dir: Path) -> dict:
    """Judge a saved run (again) and write the outcome into its result.json."""
    result = judge(result_dir)
    (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


# ---------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="run all 5 test goals")
    parser.add_argument("--instance", action="append", choices=NAMES, default=[],
                        help="run one test goal (repeat for more)")
    parser.add_argument("--runs", type=int, default=1, help="runs per test goal (default 1)")
    parser.add_argument("--model", default="haiku", help="model to run (default haiku)")
    parser.add_argument("--plugin-dir", type=Path, default=REPO,
                        help="Goals checkout to load as the plugin (default: this repo)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="keep each run's temp folder for debugging")
    parser.add_argument("--recheck", nargs="*", type=Path, metavar="RESULT_DIR",
                        help="judge saved runs again, no model call (default: all of them)")
    args = parser.parse_args(argv)

    if args.recheck is not None:
        folders = args.recheck or sorted(p.parent for p in RESULTS.glob("*/result.json"))
        for folder in folders:
            result = recheck(folder)
            print(folder.name, " ".join(f"{c['name']}={c['verdict']}" for c in result["checks"]))
        return 0

    names = NAMES if args.all else args.instance
    if not names:
        parser.error("say what to run: --all, --instance NAME, or --recheck")
    claude_bin = shutil.which("claude")
    if not claude_bin:
        parser.error("`claude` was not found on PATH")
    tested = code_under_test(args.plugin_dir.resolve(), claude_bin)
    cli = tested["goals_cli"]
    print(f"plugin folder: {tested['plugin_dir']} at {tested['plugin_commit']}")
    print(f"goals CLI:     {cli['path']} (source {cli['source']} at {cli['source_commit']})")
    if not cli["matches_plugin_dir"]:
        print("WARNING: the `goals` CLI on PATH is not the code in the plugin folder.")
    for name in names:
        for run_no in range(1, args.runs + 1):
            print(f"{name} run {run_no} ...", flush=True)
            folder = run_instance(name, run_no=run_no, model=args.model, tested=tested,
                                  plugin_dir=args.plugin_dir, claude_bin=claude_bin,
                                  keep_temp=args.keep_temp)
            result = json.loads((folder / "result.json").read_text())
            for check in result["checks"]:
                print(f"  {check['name']}: {check['verdict']}  {'; '.join(check['reasons'])}")
            print(f"  {result['seconds']} s, ${result['cost_usd'] or 0:.3f} reported, {folder}")
    print("Table: uv run python bench/report.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
