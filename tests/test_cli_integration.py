import json
import subprocess
from pathlib import Path

from goals.models import Event, EventType


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )


def run_unchecked(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
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
        "plugins.yml": "plugins",
        "profiles.yml": "profiles",
        "skills.yml": "skills",
    }
    for name, kind in registry_kinds.items():
        (registry_root / name).write_text(f"version: 1\nkind: {kind}\n{kind}: {{}}\n")
    run(["git", "add", "README.md", "LICENSE", "registries"], path)
    run(["git", "commit", "-m", "init"], path)


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
    assert "goals boundary explain --domain auto" in run_prompt.stdout
    assert "goals source citations" in run_prompt.stdout
    assert "goals source freshness" in run_prompt.stdout
    assert "goals asset provenance" in run_prompt.stdout
    assert "goals creative compare" in run_prompt.stdout
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
    assert "registries=6" in validate.stdout
    ecosystem = run(["python", "-m", "goals.cli", "ecosystem", "recommend"], worktree)
    assert "skill:" in ecosystem.stdout or "plugin:" in ecosystem.stdout
    merged_ecosystem = run(["python", "-m", "goals.cli", "ecosystem", "merge"], worktree)
    assert "Cross-Agent Ecosystem Recommendation Merge" in merged_ecosystem.stdout
    assert "supported by 2 agent(s)" in merged_ecosystem.stdout
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
    boundary = run(
        [
            "python",
            "-m",
            "goals.cli",
            "boundary",
            "explain",
            "--domain",
            "financial",
            "--level",
            "basic",
        ],
        worktree,
    )
    assert "Professional Boundary" in boundary.stdout
    assert "financial" in boundary.stdout
    assert "money or long-term obligations" in boundary.stdout
    audit = run(["python", "-m", "goals.cli", "ecosystem", "audit"], worktree)
    assert "Ecosystem Quality Audit" in audit.stdout
    skill_root = tmp_path / "skills"
    local_skill = skill_root / "migration-helper"
    local_skill.mkdir(parents=True)
    (local_skill / "SKILL.md").write_text(
        "---\nname: Migration Helper\n"
        "description: Helps coordinate database migrations safely.\n---\n"
    )
    plugin_root = tmp_path / "plugins"
    local_plugin = plugin_root / "customer-research" / ".codex-plugin"
    local_plugin.mkdir(parents=True)
    (local_plugin / "plugin.json").write_text(
        json.dumps(
            {
                "name": "@acme/customer-research",
                "displayName": "Customer Research",
                "description": "Finds and summarizes customer research sources.",
                "keywords": ["research", "sources"],
            }
        )
    )
    discovered = run(
        [
            "python",
            "-m",
            "goals.cli",
            "ecosystem",
            "discover",
            "--skill-root",
            str(skill_root),
            "--plugin-root",
            str(plugin_root),
        ],
        worktree,
    )
    assert "migration-helper" in discovered.stdout
    assert "customer-research" in discovered.stdout
    assert str(tmp_path) not in discovered.stdout
    sync = run(
        [
            "python",
            "-m",
            "goals.cli",
            "ecosystem",
            "sync",
            "--skill-root",
            str(skill_root),
            "--plugin-root",
            str(plugin_root),
        ],
        worktree,
    )
    assert "dry run" in sync.stdout
    assert "migration-helper" in sync.stdout
    assert "customer-research" in sync.stdout
    assert "migration-helper" not in (worktree / "registries" / "skills.yml").read_text()
    assert "customer-research" not in (worktree / "registries" / "plugins.yml").read_text()
    sync_apply = run(
        [
            "python",
            "-m",
            "goals.cli",
            "ecosystem",
            "sync",
            "--skill-root",
            str(skill_root),
            "--plugin-root",
            str(plugin_root),
            "--apply",
        ],
        worktree,
    )
    assert "Applied" in sync_apply.stdout
    assert "migration-helper" in (worktree / "registries" / "skills.yml").read_text()
    assert "customer-research" in (worktree / "registries" / "plugins.yml").read_text()
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
    source_citations = run(["python", "-m", "goals.cli", "source", "citations"], worktree)
    assert "Citation Quality Report" in source_citations.stdout
    assert "Overall: pass" in source_citations.stdout
    asset = run(
        [
            "python",
            "-m",
            "goals.cli",
            "asset",
            "add",
            "Hero image",
            "--locator",
            "assets/hero.png",
            "--asset-type",
            "image",
            "--origin",
            "generated",
            "--creator-tool",
            "image-model",
            "--usage-rights",
            "allowed",
            "--prompt",
            "Simple product hero",
        ],
        worktree,
    )
    assert "Recorded asset: AST-" in asset.stdout
    asset_id = asset.stdout.strip().split(": ", 1)[1]
    asset_list = run(["python", "-m", "goals.cli", "asset", "list"], worktree)
    assert "Hero image" in asset_list.stdout
    asset_provenance = run(["python", "-m", "goals.cli", "asset", "provenance"], worktree)
    assert "Asset Provenance Report" in asset_provenance.stdout
    assert "Overall: pass" in asset_provenance.stdout
    creative_a = run(
        [
            "python",
            "-m",
            "goals.cli",
            "creative",
            "variant",
            "add",
            "Calm launch",
            "--summary",
            "Plain, trust-building campaign direction.",
            "--best-for",
            "non-technical buyers",
            "--asset-id",
            asset_id,
            "--score",
            "brand_fit=5:Matches the product tone",
            "--score",
            "clarity=5:Easy to understand",
            "--strength",
            "Clear and low-risk.",
            "--status",
            "selected",
        ],
        worktree,
    )
    assert "Recorded creative variant: VAR-" in creative_a.stdout
    creative_b = run(
        [
            "python",
            "-m",
            "goals.cli",
            "creative",
            "variant",
            "add",
            "Bold launch",
            "--summary",
            "Higher-energy campaign direction.",
            "--best-for",
            "awareness push",
            "--score",
            "brand_fit=3:May be louder than the brand",
            "--score",
            "clarity=4:Still understandable",
            "--risk",
            "Could feel too salesy.",
            "--status",
            "rejected",
        ],
        worktree,
    )
    assert "Recorded creative variant: VAR-" in creative_b.stdout
    creative_list = run(["python", "-m", "goals.cli", "creative", "variants"], worktree)
    assert "Calm launch" in creative_list.stdout
    creative_compare = run(["python", "-m", "goals.cli", "creative", "compare"], worktree)
    assert "Creative Variant Comparison" in creative_compare.stdout
    assert "Overall: pass" in creative_compare.stdout
    refreshed_dash = run(["python", "-m", "goals.cli", "dashboard"], worktree)
    assert "Creative Variants" in Path(refreshed_dash.stdout.strip()).read_text()
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
    eval_result = run(
        ["python", "-m", "goals.cli", "eval", "scenarios", "--adapter", "claude"], worktree
    )
    assert "personal-fitness-reset: pass" in eval_result.stdout
    assert "ecosystem-skill-plugin-routing: pass" in eval_result.stdout
    dogfood = run(["python", "-m", "goals.cli", "eval", "dogfood", "--adapter", "claude"], worktree)
    assert "Goals Dogfood Report" in dogfood.stdout
    assert "What the user sees" in dogfood.stdout
    assert "Proof required" in dogfood.stdout
    assert "ecosystem-skill-plugin-routing: pass" in dogfood.stdout
    coverage = run(
        ["python", "-m", "goals.cli", "eval", "coverage", "--adapter", "claude"], worktree
    )
    assert "Goal Use-Case Coverage Report" in coverage.stdout
    assert "technical-repo-change: covered" in coverage.stdout
    assert "high-stakes-boundary: covered" in coverage.stdout
    rehearsal = run(
        ["python", "-m", "goals.cli", "eval", "rehearsal", "--adapter", "claude"], worktree
    )
    assert "Goal Lifecycle Rehearsal Report" in rehearsal.stdout
    assert "personal-fitness-reset: pass" in rehearsal.stdout
    assert "business-research-brief: pass" in rehearsal.stdout
    issue_stress = run(
        ["python", "-m", "goals.cli", "eval", "issue-stress", "--adapter", "claude"],
        worktree,
    )
    assert "Goal Issue Stress Report" in issue_stress.stdout
    assert "decision-filter: pass" in issue_stress.stdout
    assert "unsafe-review-escalation: pass" in issue_stress.stdout
    self_check = run(
        ["python", "-m", "goals.cli", "eval", "self-check", "--adapter", "claude"],
        worktree,
    )
    assert "Goals Self-Check Report" in self_check.stdout
    assert "Recommended Next Slices" in self_check.stdout
    roadmap = run(
        ["python", "-m", "goals.cli", "roadmap", "suggest", "--adapter", "claude"],
        worktree,
    )
    assert "Roadmap Update Plan" in roadmap.stdout
    assert "Patch Preview" in roadmap.stdout
    roadmap_apply = run(
        ["python", "-m", "goals.cli", "roadmap", "suggest", "--adapter", "claude", "--apply"],
        worktree,
    )
    assert "Mode: applied" in roadmap_apply.stdout
    roadmap_file = worktree / "ROADMAP.md"
    assert "<!-- goals:self-check-roadmap:start -->" in roadmap_file.read_text()
    local_safety = run(
        ["python", "-m", "goals.cli", "safety-check", "--mode", "local", "."], worktree
    )
    assert "public_repo_hygiene: pass" in local_safety.stdout
    publish_safety = run_unchecked(
        ["python", "-m", "goals.cli", "safety-check", "--mode", "publish", "."], worktree
    )
    assert publish_safety.returncode == 1
    assert "public_repo_hygiene: fail" in publish_safety.stdout


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
        {"checks_run": ["pytest"], "acceptance_met": ["done"], "confidence": 0.9, "notes": "done"}
    )
    evidence_file = worktree / "evidence.json"
    evidence_file.write_text(evidence)
    run(["python", "-m", "goals.cli", "phase", "start", "P1"], worktree)
    run(
        ["python", "-m", "goals.cli", "phase", "evidence", "P1", "--file", str(evidence_file)],
        worktree,
    )
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
