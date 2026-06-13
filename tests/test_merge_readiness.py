from pathlib import Path
import subprocess

from goals.issues import analyze_goal_issues
from goals.merge_readiness import analyze_merge_readiness, render_merge_readiness_report
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


def test_merge_readiness_flags_migration_file_without_ordering_proof(tmp_path) -> None:
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["db/migrations/0102_add_tags.py"],
            checks_run=["pytest"],
            acceptance_met=["Tags work."],
            confidence=0.9,
        ),
    )

    report = analyze_merge_readiness(snapshot)
    issues = analyze_goal_issues(snapshot)
    rendered = render_merge_readiness_report(report)

    assert report.passed is True
    assert report.user_questions == []
    assert any(finding.area == "migration" for finding in report.findings)
    assert any("migration-order" in action for action in report.agent_actions)
    assert any(issue.area == "merge" for issue in issues.issues)
    assert "Goal Merge Readiness Report" in rendered


def test_merge_readiness_accepts_recorded_migration_ordering_proof(tmp_path) -> None:
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["alembic/versions/0102_add_tags.py"],
            checks_run=["pytest", "alembic heads confirmed single head"],
            acceptance_met=["Migration ordering verified against main."],
            confidence=0.9,
        ),
    )

    report = analyze_merge_readiness(snapshot)

    assert report.findings == []
    assert report.passed is True


def test_merge_readiness_does_not_treat_known_gap_as_ordering_proof(tmp_path) -> None:
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["db/migrations/0102_add_tags.py"],
            checks_run=["pytest"],
            acceptance_met=["Feature works."],
            known_gaps=["Migration ordering is unclear."],
            confidence=0.9,
        ),
    )

    report = analyze_merge_readiness(snapshot)

    assert any(finding.area == "migration" for finding in report.findings)


def test_merge_readiness_flags_parallel_worktree_without_reconciliation(tmp_path) -> None:
    snapshot = _snapshot(
        tmp_path,
        mode="parallel",
        evidence=Evidence(
            changed_files=["src/app.py"],
            checks_run=["pytest"],
            acceptance_met=["Feature works."],
            confidence=0.9,
        ),
    )

    report = analyze_merge_readiness(snapshot)

    assert any(finding.area == "parallel" for finding in report.findings)
    assert report.user_questions == []
    assert any("coordinator" in action for action in report.agent_actions)


def test_merge_readiness_scans_parallel_worktree_file_overlap(tmp_path) -> None:
    repo = _init_repo(tmp_path / "repo")
    active = tmp_path / "active"
    worker = tmp_path / "worker"
    _run(["git", "worktree", "add", "-b", "goal/active", str(active)], repo)
    _run(["git", "worktree", "add", "-b", "goal/worker", str(worker)], repo)
    (active / "src" / "app.py").write_text("active = True\n")
    _run(["git", "add", "src/app.py"], active)
    _run(["git", "commit", "-m", "active change"], active)
    (worker / "src" / "app.py").write_text("worker = True\n")
    _run(["git", "add", "src/app.py"], worker)
    _run(["git", "commit", "-m", "worker change"], worker)
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["src/app.py"],
            checks_run=["pytest"],
            acceptance_met=["Feature works."],
            confidence=0.9,
        ),
        mode="parallel",
        base_repo=repo,
        worktree_path=active,
        branch="goal/active",
    )

    report = analyze_merge_readiness(snapshot)
    rendered = render_merge_readiness_report(report)

    assert report.parallel_scan is not None
    assert report.parallel_scan.overlapping_files == ["src/app.py"]
    assert any("same files" in finding.summary for finding in report.findings)
    assert report.user_questions == []
    assert "Parallel Worktree Scan" in rendered
    assert str(tmp_path) not in rendered


def test_merge_readiness_scans_parallel_migration_numbering_risk(tmp_path) -> None:
    repo = _init_repo(tmp_path / "repo")
    active = tmp_path / "active"
    worker = tmp_path / "worker"
    _run(["git", "worktree", "add", "-b", "goal/active", str(active)], repo)
    _run(["git", "worktree", "add", "-b", "goal/worker", str(worker)], repo)
    (active / "db" / "migrations").mkdir(parents=True)
    (active / "db" / "migrations" / "0101_add_tags.py").write_text("# active\n")
    _run(["git", "add", "db/migrations/0101_add_tags.py"], active)
    _run(["git", "commit", "-m", "active migration"], active)
    (worker / "db" / "migrations").mkdir(parents=True)
    (worker / "db" / "migrations" / "0102_add_owner.py").write_text("# worker\n")
    _run(["git", "add", "db/migrations/0102_add_owner.py"], worker)
    _run(["git", "commit", "-m", "worker migration"], worker)
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["db/migrations/0101_add_tags.py"],
            checks_run=["pytest"],
            acceptance_met=["Feature works."],
            confidence=0.9,
        ),
        mode="parallel",
        base_repo=repo,
        worktree_path=active,
        branch="goal/active",
    )

    report = analyze_merge_readiness(snapshot)

    assert report.parallel_scan is not None
    assert report.parallel_scan.overlapping_migrations == [
        "db/migrations/0101_add_tags.py",
        "db/migrations/0102_add_owner.py",
    ]
    assert any("overlapping migration" in finding.summary for finding in report.findings)
    assert any("migration-order proof" in action for action in report.agent_actions)
    assert report.user_questions == []


def test_merge_readiness_scans_dirty_parallel_worktree(tmp_path) -> None:
    repo = _init_repo(tmp_path / "repo")
    active = tmp_path / "active"
    worker = tmp_path / "worker"
    _run(["git", "worktree", "add", "-b", "goal/active", str(active)], repo)
    _run(["git", "worktree", "add", "-b", "goal/worker", str(worker)], repo)
    (worker / "README.md").write_text("# Demo\n\nDirty worker notes.\n")
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["src/app.py"],
            checks_run=["pytest"],
            acceptance_met=["Feature works."],
            confidence=0.9,
        ),
        mode="parallel",
        base_repo=repo,
        worktree_path=active,
        branch="goal/active",
    )

    report = analyze_merge_readiness(snapshot)

    assert report.parallel_scan is not None
    assert report.parallel_scan.sibling_worktrees[0].dirty is True
    assert any("uncommitted changes" in finding.summary for finding in report.findings)
    assert report.user_questions == []


def test_merge_readiness_surfaces_uncovered_high_risk_merge_decision(tmp_path) -> None:
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["src/app.py"],
            checks_run=["pytest"],
            acceptance_met=["Feature works."],
            confidence=0.9,
        ),
        risks=["Production data migration approval is needed before merge."],
    )

    report = analyze_merge_readiness(snapshot)

    assert report.passed is False
    assert report.user_questions == ["Merge risk may need user approval."]
    assert any(finding.needs_user for finding in report.findings)


def test_merge_readiness_does_not_duplicate_existing_user_decision(tmp_path) -> None:
    snapshot = _snapshot(
        tmp_path,
        evidence=Evidence(
            changed_files=["src/app.py"],
            checks_run=["pytest"],
            acceptance_met=["Feature works."],
            confidence=0.9,
        ),
        risks=["Production data migration approval is needed before merge."],
        decisions=[
            Decision(
                title="Production migration approval",
                plain_summary="Choose whether to allow the production data migration.",
                why_it_matters="Production data changes may be irreversible.",
                recommendation="Do not merge until approved.",
                options=[
                    DecisionOption(
                        label="Approve migration",
                        explanation="Allow the production data change.",
                        risk="high",
                        reversible=False,
                    )
                ],
                priority="blocking",
                suggested_reply="Do not merge until approved.",
            )
        ],
    )

    report = analyze_merge_readiness(snapshot)

    assert report.passed is True
    assert report.user_questions == []


def _snapshot(
    tmp_path,
    *,
    evidence: Evidence,
    mode: str = "single",
    risks: list[str] | None = None,
    decisions: list[Decision] | None = None,
    base_repo: Path | None = None,
    worktree_path: Path | None = None,
    branch: str = "goal/demo",
) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Add tags to tasks",
        definition_of_done=["Ready to merge."],
        topology=WorktreeLease(
            mode=mode,
            base_repo=str(base_repo or tmp_path),
            base_branch="main",
            worktree_path=str(worktree_path or tmp_path),
            branch=branch,
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Implementation",
                goal="Implement and prove the change.",
                status=PhaseStatus.ACCEPTED,
                evidence=evidence,
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.PASS,
                        summary="ok",
                    )
                ],
            )
        ],
        current_phase=None,
        status="complete",
        risks=risks or [],
        decisions=decisions or [],
    )


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _run(["git", "init", "-b", "main"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("base = True\n")
    (path / "README.md").write_text("# Demo\n")
    _run(["git", "add", "README.md", "src/app.py"], path)
    _run(["git", "commit", "-m", "init"], path)
    return path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
