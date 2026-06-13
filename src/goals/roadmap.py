from __future__ import annotations

from pathlib import Path
import re

from goals.evaluations import run_self_check
from goals.models import RoadmapSuggestion, RoadmapUpdatePlan, SelfCheckReport
from goals.storage import atomic_write_text

START_MARKER = "<!-- goals:self-check-roadmap:start -->"
END_MARKER = "<!-- goals:self-check-roadmap:end -->"

_KNOWN_CAPABILITIES = {
    "automatic gap-to-roadmap patches": "automatic_gap_to_roadmap_patch",
    "asset provenance checks": "asset_provenance_checks",
    "citation quality review": "citation_quality_review",
    "code-derived architecture checks": "code_derived_architecture_checks",
    "cross-agent recommendation merge": "cross_agent_recommendation_merge",
    "cross-project memory sync": "cross_project_memory_sync",
    "handoff owner registry": "handoff_owner_registry",
    "mandatory external review gate": "mandatory_external_review_gate",
    "optional calendar context": "optional_calendar_context",
    "parallel worktree merge gates": "parallel_worktree_merge_gates",
    "permission policy registry": "permission_policy_registry",
    "private memory boundary": "private_memory_boundary",
    "professional boundary templates": "professional_boundary_templates",
    "recurring goal templates": "recurring_goal_templates",
    "source freshness gate": "source_freshness_gate",
    "spaced recall outputs": "spaced_recall_outputs",
}


def plan_roadmap_update(
    worktree: Path,
    *,
    report: SelfCheckReport | None = None,
    path: Path | None = None,
    adapters: list[str] | None = None,
    max_user_decisions: int = 2,
) -> RoadmapUpdatePlan:
    target = _roadmap_path(worktree, path)
    self_check = report or run_self_check(
        worktree,
        adapters=adapters,
        max_user_decisions=max_user_decisions,
    )
    suggestions = suggestions_from_self_check(self_check)
    plan = RoadmapUpdatePlan(
        path=_display_path(worktree, target),
        dry_run=True,
        summary=f"Prepared {len(suggestions)} roadmap suggestion(s) from self-check.",
        suggestions=suggestions,
    )
    return plan.model_copy(update={"patch_preview": render_generated_section(plan)})


def suggestions_from_self_check(report: SelfCheckReport) -> list[RoadmapSuggestion]:
    suggestions = []
    for index, next_slice in enumerate(report.next_slices):
        kind, label = _parse_next_slice(next_slice)
        capability = _capability_name(label)
        title = _title_from_label(label)
        priority = "p0" if kind == "gap" else ("p1" if index == 0 else "p2")
        suggestions.append(
            RoadmapSuggestion(
                suggestion_id=f"self-check-{capability}",
                title=title,
                plain_summary=(
                    f"Self-check recommends {label} as a next product capability "
                    "that would make Goals better at finishing broad goals."
                ),
                capability=capability,
                recommended_change=_recommended_change(kind, label),
                priority=priority,  # type: ignore[arg-type]
                evidence_refs=[f"self-check.next_slices[{index}]", "self-check.summary"],
            )
        )
    return suggestions


def apply_roadmap_update(worktree: Path, plan: RoadmapUpdatePlan) -> RoadmapUpdatePlan:
    target = _roadmap_path(worktree, Path(plan.path))
    current = target.read_text(encoding="utf-8") if target.exists() else "# Roadmap\n"
    next_text = upsert_generated_section(current, plan.patch_preview)
    atomic_write_text(target, next_text)
    return plan.model_copy(
        update={
            "dry_run": False,
            "summary": f"Applied {len(plan.suggestions)} roadmap suggestion(s) to {plan.path}.",
        }
    )


def upsert_generated_section(current: str, generated_section: str) -> str:
    current = current.rstrip() + "\n"
    if START_MARKER in current and END_MARKER in current:
        pattern = re.compile(
            rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
            flags=re.DOTALL,
        )
        return pattern.sub(generated_section.rstrip(), current).rstrip() + "\n"
    return current + "\n" + generated_section.rstrip() + "\n"


def render_roadmap_update_plan(plan: RoadmapUpdatePlan) -> str:
    mode = "dry run" if plan.dry_run else "applied"
    lines = [
        "# Roadmap Update Plan",
        "",
        f"Mode: {mode}",
        f"Path: {plan.path}",
        "",
        plan.summary,
        "",
        "## Suggestions",
        "",
    ]
    if not plan.suggestions:
        lines.append("- No roadmap suggestions found.")
    for suggestion in plan.suggestions:
        lines.extend(
            [
                f"- **{suggestion.title}** ({suggestion.priority})",
                f"  - Summary: {suggestion.plain_summary}",
                f"  - Recommended change: {suggestion.recommended_change}",
                f"  - Capability: `{suggestion.capability}`",
            ]
        )
    lines.extend(["", "## Patch Preview", "", "```markdown", plan.patch_preview.rstrip(), "```"])
    return "\n".join(lines) + "\n"


def render_generated_section(plan: RoadmapUpdatePlan) -> str:
    lines = [
        START_MARKER,
        "## Goals Self-Check Suggestions",
        "",
        "This generated section is safe to refresh. It turns self-check findings into roadmap candidates without changing human-written roadmap notes.",
        "",
    ]
    if not plan.suggestions:
        lines.append("- No roadmap update needed from the latest self-check.")
    for suggestion in plan.suggestions:
        lines.extend(
            [
                f"- **{suggestion.title}** (`{suggestion.priority}`)",
                f"  - Source: {suggestion.source}",
                f"  - Capability: `{suggestion.capability}`",
                f"  - Why: {suggestion.plain_summary}",
                f"  - Recommended change: {suggestion.recommended_change}",
                f"  - Evidence: {', '.join(f'`{item}`' for item in suggestion.evidence_refs)}",
            ]
        )
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def _roadmap_path(worktree: Path, path: Path | None) -> Path:
    target = path or Path("ROADMAP.md")
    if target.is_absolute():
        return target
    return worktree / target


def _display_path(worktree: Path, target: Path) -> str:
    try:
        return str(target.resolve().relative_to(worktree.resolve()))
    except ValueError:
        return target.name


def _parse_next_slice(next_slice: str) -> tuple[str, str]:
    gap_prefix = "Close current capability gap: "
    planned_prefix = "Explore planned capability: "
    if next_slice.startswith(gap_prefix):
        return "gap", next_slice.removeprefix(gap_prefix)
    if next_slice.startswith(planned_prefix):
        return "planned", next_slice.removeprefix(planned_prefix)
    return "planned", next_slice


def _capability_name(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in _KNOWN_CAPABILITIES:
        return _KNOWN_CAPABILITIES[normalized]
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "unknown_capability"


def _title_from_label(label: str) -> str:
    return label.replace("-", " ").title().replace("To", "to")


def _recommended_change(kind: str, label: str) -> str:
    if kind == "gap":
        return (
            f"Close the current {label} gap with product behavior, tests, docs, "
            "and a validation command before expanding the roadmap."
        )
    return (
        f"Define the smallest user-visible {label} slice, add self-check coverage, "
        "and keep any write behavior dry-run-first until reviewed."
    )
