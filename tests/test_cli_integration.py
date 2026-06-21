import json
import os
import subprocess
from pathlib import Path

from goals.loop_builder import LoopDesign, LoopPhase
from goals.models import Event, EventType, Evidence, GateResult, GateVerdict, GoalSnapshot, GoalStatus, Phase, PhaseStatus, WorktreeLease
from goals.storage import EventStore


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )


def run_unchecked(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )


def run_with_env(
    cmd: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        env=merged,
    )


def init_repo(path: Path) -> None:
    run(["git", "init"], path)
    run(["git", "config", "user.email", "test@example.com"], path)
    run(["git", "config", "user.name", "Test User"], path)
    (path / "README.md").write_text("# Demo\n")
    (path / "LICENSE").write_text("MIT\n")
    registry_root = path / "registries"
    registry_root.mkdir()
    registry_kinds = {
        "adapters.yml": "adapters",
        "agents.yml": "agents",
        "gates.yml": "gates",
        "profiles.yml": "profiles",
    }
    for name, kind in registry_kinds.items():
        (registry_root / name).write_text(f"version: 1\nkind: {kind}\n{kind}: {{}}\n")
    run(["git", "add", "README.md", "LICENSE", "registries"], path)
    run(["git", "commit", "-m", "init"], path)


def test_final_phase_accept_prints_user_interview_once(tmp_path: Path) -> None:
    goal_dir = tmp_path / ".agent-workflow" / "goals" / "demo"
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Finish tiny goal",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="",
            worktree_path=str(tmp_path),
            branch="",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Only phase",
                goal="Finish",
                evidence=Evidence(checks_run=["manual"], acceptance_met=["done"], confidence=0.9),
                reviews=[
                    GateResult(gate_id="phase-review", verdict=GateVerdict.PASS, summary="ok")
                ],
            )
        ],
        current_phase="P1",
    )
    EventStore(goal_dir).append(
        Event(
            goal_id="demo",
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": snapshot.model_dump()},
        )
    )
    env = {"GOALS_HOME": str(tmp_path / "goals-home")}

    first = run_with_env(["python", "-m", "goals.cli", "phase", "accept", "P1"], tmp_path, env)
    second = run_with_env(["python", "-m", "goals.cli", "phase", "accept", "P1"], tmp_path, env)

    assert "Post-goal personalization interview" in first.stdout
    assert "goals user interview --goal demo" in first.stdout
    assert "Post-goal personalization interview" not in second.stdout


def test_create_status_dashboard_validate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(
        [
            "python",
            "-m",
            "goals.cli",
            "create",
            "Add tags to tasks and update tests",
            "--why",
            "Make tasks easier to organize.",
            "--adapter",
            "claude",
        ],
        repo,
    )
    assert "Created goal" in result.stdout
    assert "Adapter: claude" in result.stdout
    assert "Claude Mode A notes" in result.stdout
    worktree_line = next(
        line for line in result.stdout.splitlines() if line.startswith("Worktree:")
    )
    worktree = Path(worktree_line.split(":", 1)[1].strip())
    goal_file = next((worktree / ".agent-workflow" / "goals").glob("*/goal.json"))
    assert json.loads(goal_file.read_text())["why"] == "Make tasks easier to organize."
    exclude_path = Path(
        run(["git", "rev-parse", "--git-path", "info/exclude"], worktree).stdout.strip()
    )
    if not exclude_path.is_absolute():
        exclude_path = worktree / exclude_path
    exclude = exclude_path.read_text()
    assert ".agent-workflow/self-evolution/" in exclude
    base_exclude_path = Path(
        run(["git", "rev-parse", "--git-path", "info/exclude"], repo).stdout.strip()
    )
    if not base_exclude_path.is_absolute():
        base_exclude_path = repo / base_exclude_path
    assert ".agent-workflow/self-evolution/" in base_exclude_path.read_text()
    status = run(["python", "-m", "goals.cli", "status"], worktree)
    assert "Add tags" in status.stdout
    issues = run(["python", "-m", "goals.cli", "issues"], worktree)
    assert "Goal Issue Report" in issues.stdout
    assert "P1 has no evidence yet." in issues.stdout
    brief = run(["python", "-m", "goals.cli", "brief"], worktree)
    assert "Goal Brief" in brief.stdout
    assert "Waiting on: agent" in brief.stdout
    assert "What Needs Your Answer" in brief.stdout
    merge_check = run(["python", "-m", "goals.cli", "merge-check"], worktree)
    assert "Goal Merge Readiness Report" in merge_check.stdout
    assert "Overall: pass" in merge_check.stdout
    run_prompt = run(["python", "-m", "goals.cli", "run", "--adapter", "codex"], worktree)
    assert "Codex Mode A notes" in run_prompt.stdout
    assert "goals issues" in run_prompt.stdout
    assert "goals brief" in run_prompt.stdout
    assert "Architecture map:" in run_prompt.stdout
    assert "goals architecture check" in run_prompt.stdout
    assert "goals source freshness" in run_prompt.stdout
    dash = run(["python", "-m", "goals.cli", "dashboard"], worktree)
    assert Path(dash.stdout.strip()).exists()
    architecture = run(["python", "-m", "goals.cli", "architecture", "show"], worktree)
    architecture_path = Path(architecture.stdout.strip())
    assert architecture_path.exists()
    assert "```mermaid" in architecture_path.read_text()
    architecture_check = run(["python", "-m", "goals.cli", "architecture", "check"], worktree)
    assert "Code-Derived Architecture Check" in architecture_check.stdout
    assert "Overall: pass" in architecture_check.stdout
    validate = run(["python", "-m", "goals.cli", "validate"], worktree)
    assert "Validated goal" in validate.stdout
    assert "registries=4" in validate.stdout
    skills = run(["python", "-m", "goals.cli", "skills", "list"], worktree)
    assert "goals-decision-explainer" in skills.stdout
    permission = run(
        [
            "python",
            "-m",
            "goals.cli",
            "permission",
            "check",
            "github",
            "--kind",
            "plugin",
            "--action",
            "inspect a remote issue",
        ],
        worktree,
    )
    assert "Permission Policy Report" in permission.stdout
    assert "Needs The User" in permission.stdout
    assert "Approve use of this external service or connector?" in permission.stdout
    source = run(
        [
            "python",
            "-m",
            "goals.cli",
            "source",
            "add",
            "Customer interview",
            "--locator",
            "interview-001",
            "--source-type",
            "interview",
            "--summary",
            "Customer wants simple progress.",
            "--credibility",
            "high",
            "--claim",
            "Users need plain-language progress.",
            "--confidence",
            "0.8",
        ],
        worktree,
    )
    assert "Recorded source: SRC-" in source.stdout
    source_list = run(["python", "-m", "goals.cli", "source", "list"], worktree)
    assert "Customer interview" in source_list.stdout
    assert "Users need plain-language progress." in source_list.stdout
    source_freshness = run(["python", "-m", "goals.cli", "source", "freshness"], worktree)
    assert "Source Freshness Report" in source_freshness.stdout
    assert "Overall: pass" in source_freshness.stdout
    refreshed_dash = run(["python", "-m", "goals.cli", "dashboard"], worktree)
    dashboard_text = Path(refreshed_dash.stdout.strip()).read_text()
    assert "Sources" in dashboard_text
    assert "Customer interview" in dashboard_text
    run(
        [
            "python",
            "-m",
            "goals.cli",
            "memory",
            "record",
            "Repeated friction choosing the right skill.",
            "--area",
            "skill",
            "--kind",
            "friction",
        ],
        worktree,
    )
    memory = run(
        [
            "python",
            "-m",
            "goals.cli",
            "memory",
            "record",
            "Repeated friction choosing the right skill again.",
            "--area",
            "skill",
            "--kind",
            "friction",
        ],
        worktree,
    )
    assert "Improve or add a skill" in memory.stdout
    suggestions = run(["python", "-m", "goals.cli", "memory", "suggest"], worktree)
    assert "Improve or add a skill" in suggestions.stdout
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    init_repo(source_repo)
    run(
        [
            "python",
            "-m",
            "goals.cli",
            "memory",
            "record",
            "Private client Alpha repeatedly missed setup evidence.",
            "--area",
            "skill",
            "--kind",
            "friction",
        ],
        source_repo,
    )
    run(
        [
            "python",
            "-m",
            "goals.cli",
            "memory",
            "record",
            "Private client Alpha missed setup evidence again.",
            "--area",
            "skill",
            "--kind",
            "friction",
        ],
        source_repo,
    )
    memory_sync = run(
        ["python", "-m", "goals.cli", "memory", "sync", str(source_repo)],
        worktree,
    )
    assert "Cross-Project Memory Sync" in memory_sync.stdout
    assert "dry run" in memory_sync.stdout
    assert "Private client Alpha" not in memory_sync.stdout
    memory_sync_apply = run(
        ["python", "-m", "goals.cli", "memory", "sync", str(source_repo), "--apply"],
        worktree,
    )
    assert "Imported 1 cross-project memory suggestion" in memory_sync_apply.stdout
    synced_suggestions = run(["python", "-m", "goals.cli", "memory", "suggest"], worktree)
    assert "Cross-project learning from external-project" in synced_suggestions.stdout


def test_simple_workflow_commands(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    started = run(
        [
            "python",
            "-m",
            "goals.cli",
            "start",
            "Improve onboarding docs",
            "--why",
            "Make the happy path easy to follow.",
            "--agent",
            "codex",
        ],
        repo,
    )
    assert "# Goal Started" in started.stdout
    assert "goals next --agent codex" in started.stdout
    assert "Paste the output into Codex" in started.stdout
    assert "Required loop" not in started.stdout

    worktree_line = next(
        line for line in started.stdout.splitlines() if line.startswith("Worktree:")
    )
    worktree = Path(worktree_line.split("`", 2)[1])

    next_prompt = run(["python", "-m", "goals.cli", "next", "--agent", "claude"], worktree)
    assert "/goal Finish this Goals-managed task: Improve onboarding docs" in next_prompt.stdout
    assert "Claude Mode A notes" in next_prompt.stdout
    assert "goals brief" in next_prompt.stdout
    assert "uv run goals brief" not in next_prompt.stdout

    checked = run(["python", "-m", "goals.cli", "check"], worktree)
    assert "# Goal Check" in checked.stdout
    assert "Overall: needs attention" in checked.stdout
    assert "P1 has no evidence yet." in checked.stdout
    assert "Useful next commands:" in checked.stdout

    strict = run_unchecked(["python", "-m", "goals.cli", "check", "--strict"], worktree)
    assert strict.returncode == 1

    viewed = run(["python", "-m", "goals.cli", "view"], worktree)
    assert "# Goal View" in viewed.stdout
    assert "Dashboard:" in viewed.stdout
    assert "Architecture map:" in viewed.stdout


def test_checkpoint_cli_blocks_review_and_acceptance(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(
        [
            "python",
            "-m",
            "goals.cli",
            "create",
            "Add tags to tasks and update tests",
            "--adapter",
            "claude",
        ],
        repo,
    )
    worktree_line = next(
        line for line in result.stdout.splitlines() if line.startswith("Worktree:")
    )
    worktree = Path(worktree_line.split(":", 1)[1].strip())

    run(
        [
            "python",
            "-m",
            "goals.cli",
            "checkpoint",
            "record",
            "P1",
            "CP-plan",
            "--title",
            "Confirm the plan",
            "--kind",
            "human_validation",
            "--status",
            "needs_user",
            "--needs-user",
            "--summary",
            "The user needs to confirm the plan before review.",
        ],
        worktree,
    )

    current = run(["python", "-m", "goals.cli", "checkpoint", "current"], worktree)
    assert "Current Checkpoint" in current.stdout
    assert "Confirm the plan" in current.stdout
    assert "Waiting on: you" in current.stdout
    issues = run(["python", "-m", "goals.cli", "issues"], worktree)
    assert "Needs The User" in issues.stdout
    assert "Confirm the plan" in issues.stdout
    brief = run(["python", "-m", "goals.cli", "brief"], worktree)
    assert "Current Checkpoint" in brief.stdout
    assert "Waiting on: you" in brief.stdout

    blocked_review = run_unchecked(["python", "-m", "goals.cli", "phase", "review", "P1"], worktree)
    assert blocked_review.returncode == 1
    assert "needs_human" in blocked_review.stdout

    run(
        [
            "python",
            "-m",
            "goals.cli",
            "checkpoint",
            "waive",
            "P1",
            "CP-plan",
            "--reason",
            "User confirmed the plan in chat.",
        ],
        worktree,
    )
    evidence_file = worktree / "evidence.json"
    evidence_file.write_text(
        json.dumps(
                {
                    "checks_run": ["pytest"],
                    "acceptance_met": ["Plan confirmed."],
                    "confidence": 0.9,
                    "verifications": [
                        {"covers": "P1.C1", "kind": "auto", "command": "true"},
                        {"covers": "P1.C2", "kind": "auto", "command": "true"},
                        {"covers": "P1.C3", "kind": "auto", "command": "true"},
                    ],
                }
            )
    )
    run(
        [
            "python",
            "-m",
            "goals.cli",
            "phase",
            "evidence",
            "P1",
            "--file",
            str(evidence_file),
        ],
        worktree,
    )
    run(["python", "-m", "goals.cli", "phase", "verify", "P1"], worktree)
    review = run(["python", "-m", "goals.cli", "phase", "review", "P1"], worktree)
    assert "pass" in review.stdout

    run(
        [
            "python",
            "-m",
            "goals.cli",
            "checkpoint",
            "record",
            "P1",
            "CP-late",
            "--title",
            "Late required checkpoint",
            "--status",
            "pending",
        ],
        worktree,
    )
    blocked_accept = run_unchecked(["python", "-m", "goals.cli", "phase", "accept", "P1"], worktree)
    assert blocked_accept.returncode == 1
    assert "Required checkpoint must pass or be waived" in blocked_accept.stdout
    run(
        [
            "python",
            "-m",
            "goals.cli",
            "checkpoint",
            "waive",
            "P1",
            "CP-late",
            "--reason",
            "Covered by the passing phase review.",
        ],
        worktree,
    )
    accepted = run(["python", "-m", "goals.cli", "phase", "accept", "P1"], worktree)
    assert "Accepted phase P1" in accepted.stdout


def test_architecture_update_records_project_specific_map(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    worktree = Path(
        next(line for line in result.stdout.splitlines() if line.startswith("Worktree:"))
        .split(":", 1)[1]
        .strip()
    )
    architecture_file = worktree / "architecture.json"
    architecture_file.write_text(
        json.dumps(
            {
                "title": "Demo architecture",
                "overview": "A user-facing dashboard backed by event state.",
                "nodes": [
                    {
                        "node_id": "state",
                        "label": "Goal state",
                        "plain_summary": "Stores events and derived snapshots.",
                        "status": "built",
                        "user_value": "Keeps work resumable.",
                    },
                    {
                        "node_id": "dashboard",
                        "label": "Dashboard",
                        "plain_summary": "Shows progress and decisions.",
                        "status": "in_progress",
                        "user_value": "Makes the goal understandable.",
                    },
                ],
                "edges": [
                    {
                        "from_node": "state",
                        "to_node": "dashboard",
                        "relation": "renders",
                        "plain_summary": "State renders into the dashboard.",
                    }
                ],
            }
        )
    )

    update = run(
        [
            "python",
            "-m",
            "goals.cli",
            "architecture",
            "update",
            "--file",
            str(architecture_file),
        ],
        worktree,
    )
    output_path = Path(update.stdout.split(":", 1)[1].strip())
    text = output_path.read_text()

    assert "Updated architecture map" in update.stdout
    assert "Demo architecture" in text
    assert "State renders into the dashboard" in text
    brief = run(["python", "-m", "goals.cli", "architecture", "brief"], worktree)
    assert "Architecture Brief" in brief.stdout
    assert "Review Focus" in brief.stdout
    assert "Dashboard: In-progress node needs evidence before review or acceptance." in brief.stdout


def test_create_refuses_dirty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "dirty.txt").write_text("not committed\n")
    result = run_unchecked(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    assert result.returncode == 1
    assert "dirty working tree" in result.stdout


def test_create_refuses_branch_collision(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    run(["git", "branch", "goal/ship-demo"], repo)
    result = run_unchecked(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    assert result.returncode == 1
    assert "Branch already exists" in result.stdout


def test_validate_detects_stale_snapshot_and_repair_restores_it(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    worktree = Path(
        next(line for line in result.stdout.splitlines() if line.startswith("Worktree:"))
        .split(":", 1)[1]
        .strip()
    )
    goal_file = next((worktree / ".agent-workflow" / "goals").glob("*/goal.json"))
    snapshot = json.loads(goal_file.read_text())
    snapshot["objective"] = "Tampered outside the event log"
    goal_file.write_text(json.dumps(snapshot))

    validate = run_unchecked(["python", "-m", "goals.cli", "validate"], worktree)
    assert validate.returncode == 1
    assert "does not match the event log" in validate.stdout

    repair = run(["python", "-m", "goals.cli", "repair"], worktree)
    assert "Repaired" in repair.stdout
    validate_after_repair = run(["python", "-m", "goals.cli", "validate"], worktree)
    assert "Validated goal" in validate_after_repair.stdout


def test_phase_protocol_accepts_reviewed_phase(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    result = run(["python", "-m", "goals.cli", "create", "Ship demo"], repo)
    worktree = Path(
        next(line for line in result.stdout.splitlines() if line.startswith("Worktree:"))
        .split(":", 1)[1]
        .strip()
    )
    evidence = json.dumps(
        {
            "checks_run": ["pytest"],
            "acceptance_met": ["done"],
            "confidence": 0.9,
            "notes": "done",
            "verifications": [
                {"covers": "P1.C1", "kind": "auto", "command": "true"},
                {"covers": "P1.C2", "kind": "auto", "command": "true"},
                {"covers": "P1.C3", "kind": "auto", "command": "true"},
            ],
        }
    )
    evidence_file = worktree / "evidence.json"
    evidence_file.write_text(evidence)
    run(["python", "-m", "goals.cli", "phase", "start", "P1"], worktree)
    run(
        ["python", "-m", "goals.cli", "phase", "evidence", "P1", "--file", str(evidence_file)],
        worktree,
    )
    run(["python", "-m", "goals.cli", "phase", "verify", "P1"], worktree)
    run(["python", "-m", "goals.cli", "phase", "review", "P1"], worktree)
    accept = run(["python", "-m", "goals.cli", "phase", "accept", "P1"], worktree)
    assert "Accepted phase P1" in accept.stdout
    decision_file = worktree / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "title": "Choose storage",
                "plain_summary": "Pick where data should be stored.",
                "why_it_matters": "This can affect migrations.",
                "recommendation": "Use the existing file",
                "options": [
                    {
                        "label": "Existing file",
                        "explanation": "No migration needed.",
                        "tradeoffs": ["Less flexible."],
                        "reversible": True,
                        "risk": "low",
                    },
                    {
                        "label": "New migration",
                        "explanation": "More structured.",
                        "tradeoffs": ["Migration risk."],
                        "reversible": False,
                        "risk": "high",
                    },
                ],
                "confidence": 0.8,
                "priority": "blocking",
                "technical_details": "Migration order has to be coordinated.",
            }
        )
    )
    explanation = run(
        [
            "python",
            "-m",
            "goals.cli",
            "decision",
            "explain",
            "--file",
            str(decision_file),
            "--level",
            "detailed",
        ],
        worktree,
    )
    assert "Choose storage" in explanation.stdout
    assert "What we know so far" in explanation.stdout
    assert "Suggested reply" in explanation.stdout
    goal_id = json.loads(
        next((worktree / ".agent-workflow" / "goals").glob("*/goal.json")).read_text()
    )["goal_id"]
    append_event = Event(
        goal_id=goal_id,
        event_type=EventType.DECISION_REQUESTED,
        payload={"decision": json.loads(decision_file.read_text())},
    )
    event_log = next((worktree / ".agent-workflow" / "goals").glob("*/events.jsonl"))
    event_log.write_text(event_log.read_text() + append_event.model_dump_json() + "\n")
    run(["python", "-m", "goals.cli", "repair"], worktree)
    brief = run(["python", "-m", "goals.cli", "decision", "brief"], worktree)
    assert "Decision Brief" in brief.stdout
    assert "What Needs Your Answer" in brief.stdout
    assert "What happens next" in brief.stdout
    assert "Suggested reply" in brief.stdout


def test_finish_refuses_incomplete_goal_and_exports_complete_goal(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    init_repo(incomplete)
    started = run(["python", "-m", "goals.cli", "start", "Finish gate demo"], incomplete)
    worktree = Path(
        next(line for line in started.stdout.splitlines() if line.startswith("Worktree:"))
        .split("`", 2)[1]
    )

    not_ready = run_unchecked(["python", "-m", "goals.cli", "finish"], worktree)
    assert not_ready.returncode == 1
    assert "Goal is not complete" in not_ready.stdout

    complete = tmp_path / "complete"
    complete.mkdir()
    snapshot = GoalSnapshot(
        goal_id="done",
        objective="Done goal",
        status=GoalStatus.COMPLETE,
        definition_of_done=["Done."],
        topology=WorktreeLease(
            base_repo=str(complete),
            base_branch="",
            worktree_path=str(complete),
            branch="",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Done",
                goal="Done",
                status=PhaseStatus.ACCEPTED,
                reviews=[GateResult(gate_id="phase-review", verdict=GateVerdict.PASS, summary="ok")],
            )
        ],
        current_phase=None,
    )
    EventStore(complete / ".agent-workflow" / "goals" / "done").append(
        Event(goal_id="done", event_type=EventType.GOAL_CREATED, payload={"snapshot": snapshot.model_dump()})
    )

    finished = run(["python", "-m", "goals.cli", "finish"], complete)
    assert "Overall: pass" in finished.stdout
    assert (complete / ".goals" / "goal-state.json").is_file()


def test_loop_build_script_resets_by_default_and_append_is_explicit(tmp_path: Path) -> None:
    script = tmp_path / "loop.txt"
    script.write_text(
        "\n".join(
            [
                "objective Demo",
                "add Plan",
                "accept Plan is clear",
                "terminate Plan accepted",
                "save",
            ]
        )
    )
    out = tmp_path / ".goals"

    run(["python", "-m", "goals.cli", "loop", "build", "--out", str(out), "--script", str(script)], tmp_path)
    run(["python", "-m", "goals.cli", "loop", "build", "--out", str(out), "--script", str(script)], tmp_path)
    design = json.loads((out / "loop-design.json").read_text())
    assert len(design["phases"]) == 1

    run(
        [
            "python",
            "-m",
            "goals.cli",
            "loop",
            "build",
            "--out",
            str(out),
            "--script",
            str(script),
            "--append",
        ],
        tmp_path,
    )
    appended = json.loads((out / "loop-design.json").read_text())
    assert len(appended["phases"]) == 2


def test_loop_import_catalog_writes_design_and_expands_profiles(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "loops": [
                    {
                        "slug": "test-stabilizer-loop",
                        "title": "The test stabilizer loop",
                        "useWhen": "Use when [N] consecutive full-suite runs must pass.",
                        "verification": {
                            "title": "The full test suite passes for [N] consecutive runs.",
                            "detail": "No blind sleep or retry hides the cause.",
                        },
                        "steps": [
                            "Choose the test suite and [N].",
                            "Fix the most frequent flake.",
                        ],
                    }
                ]
            }
        )
    )
    out = tmp_path / ".goals"

    imported = run(
        [
            "python",
            "-m",
            "goals.cli",
            "loop",
            "import",
            str(catalog),
            "--out",
            str(out),
            "--select",
            "test-stabilizer-loop",
            "--answer",
            "N=3",
            "--no-prompt",
        ],
        tmp_path,
    )

    assert "Imported loop: The test stabilizer loop" in imported.stdout
    design = json.loads((out / "loop-design.json").read_text())
    assert design["objective"] == "The test stabilizer loop"
    assert "[N]" not in json.dumps(design)
    assert "imported-loop" in design["phases"][0]["validation_profiles"]
    assert design["source_metadata"]["content_sha256"]
    assert any("Evidence is recorded" in item for item in design["phases"][0]["acceptance_criteria"])
    state = json.loads((out / "goal-state.json").read_text())
    assert any(
        "Evidence is recorded against the imported loop step" in item["text"]
        for item in state["phases"][0]["acceptance_criteria"]
    )


def test_loop_import_uses_output_repo_profile_registry(tmp_path: Path) -> None:
    loop_repo = tmp_path / "loop-repo"
    loop_repo.mkdir()
    init_repo(loop_repo)
    (loop_repo / "registries" / "profiles.yml").write_text(
        "\n".join(
            [
                "version: 1",
                "kind: profiles",
                "profiles:",
                "  local-profile:",
                "    label: Local profile",
                "    acceptance_criteria:",
                "      - Imported output repo proof is recorded.",
            ]
        )
    )
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir()
    init_repo(target_repo)
    catalog = target_repo / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "title": "External profile loop",
                "profiles": ["local-profile"],
                "steps": ["Do the profiled work."],
                "verification": "Done.",
            }
        )
    )
    out = loop_repo / ".goals"

    run(
        [
            "python",
            "-m",
            "goals.cli",
            "loop",
            "import",
            str(catalog),
            "--out",
            str(out),
            "--no-prompt",
        ],
        target_repo,
    )

    state = json.loads((out / "goal-state.json").read_text())
    criteria = [item["text"] for item in state["phases"][0]["acceptance_criteria"]]
    assert "Imported output repo proof is recorded." in criteria


def test_loop_import_refuses_to_overwrite_existing_artifacts_without_force(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"title": "One", "steps": ["Do one."], "verification": "Done."}))
    out = tmp_path / ".goals"
    out.mkdir()
    (out / "loop-design.json").write_text("{}")

    refused = run_unchecked(
        [
            "python",
            "-m",
            "goals.cli",
            "loop",
            "import",
            str(catalog),
            "--out",
            str(out),
            "--no-prompt",
        ],
        tmp_path,
    )

    assert refused.returncode == 1
    assert "Refusing to overwrite" in refused.stdout


def test_loop_check_target_agent_reports_bundled_skill_not_installed(tmp_path: Path) -> None:
    script = tmp_path / "loop.txt"
    script.write_text(
        "\n".join(
            [
                "objective Skill install check",
                "add Plan",
                "accept Plan has a passing test.",
                "terminate Plan accepted.",
                "attach goals-problem-solving",
                "save",
            ]
        )
    )
    out = tmp_path / ".goals"
    isolated_home = tmp_path / "home"

    run(["python", "-m", "goals.cli", "loop", "build", "--out", str(out), "--script", str(script)], tmp_path)
    checked = run_with_env(
        [
            "python",
            "-m",
            "goals.cli",
            "loop",
            "check",
            "--out",
            str(out),
            "--target-agent",
            "codex",
        ],
        tmp_path,
        {"HOME": str(isolated_home)},
    )

    assert "skill-not-installed" in checked.stdout
    assert "goals skills install --target codex" in checked.stdout


def test_loop_activate_creates_runtime_phases_with_protocol(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    run(["git", "checkout", "-b", "feature"], repo)
    script = repo / "loop.txt"
    script.write_text(
        "\n".join(
            [
                "objective Activate loop",
                "dod Done",
                "add Plan :: Make the plan",
                "accept Plan is clear",
                "terminate Plan accepted",
                "attach goals-problem-solving",
                "profile product-ux-review",
                "save",
            ]
        )
    )
    run(["python", "-m", "goals.cli", "loop", "build", "--script", str(script)], repo)

    activated = run(["python", "-m", "goals.cli", "loop", "activate", "--in-place"], repo)
    assert "# Goal Started" in activated.stdout
    goal_file = next((repo / ".agent-workflow" / "goals").glob("*/goal.json"))
    snapshot = json.loads(goal_file.read_text())
    phase = snapshot["phases"][0]

    assert "Plan is clear" in phase["acceptance_criteria"]
    assert any("user-visible review" in item for item in phase["acceptance_criteria"])
    assert phase["protocol"]["termination_conditions"] == ["Plan accepted"]
    assert phase["protocol"]["skills"] == ["goals-problem-solving"]
    assert phase["protocol"]["validation_profiles"] == ["product-ux-review"]


def test_loop_activate_resolves_profiles_from_loop_repo_when_cwd_differs(tmp_path: Path) -> None:
    loop_repo = tmp_path / "loop-repo"
    loop_repo.mkdir()
    init_repo(loop_repo)
    (loop_repo / "registries" / "profiles.yml").write_text(
        "\n".join(
            [
                "version: 1",
                "kind: profiles",
                "profiles:",
                "  local-profile:",
                "    label: Local profile",
                "    acceptance_criteria:",
                "      - Loop repo proof is recorded.",
                "    termination_conditions:",
                "      - Loop repo stop condition is met.",
            ]
        )
    )
    loop_dir = loop_repo / ".goals"
    loop_dir.mkdir()
    design = LoopDesign(
        objective="Activate external loop",
        phases=[
            LoopPhase(
                phase_id="P1",
                title="Plan",
                acceptance_criteria=["Plan has evidence from a test."],
                validation_profiles=["local-profile"],
            )
        ],
    )
    (loop_dir / "loop-design.json").write_text(design.model_dump_json(indent=2))

    target_repo = tmp_path / "target-repo"
    target_repo.mkdir()
    init_repo(target_repo)
    run(["git", "checkout", "-b", "feature"], target_repo)
    activated = run(
        [
            "python",
            "-m",
            "goals.cli",
            "loop",
            "activate",
            "--out",
            str(loop_dir),
            "--in-place",
        ],
        target_repo,
    )

    assert "# Goal Started" in activated.stdout
    goal_file = next((target_repo / ".agent-workflow" / "goals").glob("*/goal.json"))
    snapshot = json.loads(goal_file.read_text())
    phase = snapshot["phases"][0]
    assert "Loop repo proof is recorded." in phase["acceptance_criteria"]
    assert phase["protocol"]["termination_conditions"] == ["Loop repo stop condition is met."]


def test_loop_activate_refuses_empty_design_before_creating_goal_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    run(["git", "checkout", "-b", "feature"], repo)
    script = repo / "empty-loop.txt"
    script.write_text("objective Empty loop\nsave\n")

    run(["python", "-m", "goals.cli", "loop", "build", "--script", str(script)], repo)
    activated = run_unchecked(["python", "-m", "goals.cli", "loop", "activate", "--in-place"], repo)

    assert activated.returncode == 1
    assert "at least one phase" in activated.stdout
    assert not (repo / ".agent-workflow" / "goals").exists()


def test_simulate_command_runs_regression_scenarios(tmp_path: Path) -> None:
    result = run(["python", "-m", "goals.cli", "simulate", "--strict"], tmp_path)
    assert "Goals Simulation Report" in result.stdout
    assert "Overall: pass" in result.stdout
