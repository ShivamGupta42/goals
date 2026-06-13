from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from goals.models import (
    AgentRecommendationSet,
    EcosystemRecommendation,
    EcosystemRecommendationConflict,
    EcosystemRecommendationMergeReport,
    GoalSnapshot,
    MergedEcosystemRecommendation,
    Phase,
)
from goals.permission_policy import apply_permission_to_recommendation

STOPWORDS = {
    "acceptance",
    "and",
    "are",
    "current",
    "done",
    "each",
    "for",
    "from",
    "goal",
    "has",
    "into",
    "next",
    "phase",
    "that",
    "the",
    "this",
    "turn",
    "what",
    "when",
    "with",
    "work",
}


def recommend_ecosystem_tools(
    worktree: Path,
    snapshot: GoalSnapshot,
    *,
    limit: int = 6,
) -> list[EcosystemRecommendation]:
    phase = _current_phase(snapshot)
    registry_root = _registry_root(worktree)
    candidates = []
    for kind in ("skills", "plugins"):
        path = registry_root / f"{kind}.yml"
        candidates.extend(_load_candidates(path, kind[:-1]))
    built_in_root = _built_in_registry_root()
    if not candidates and registry_root != built_in_root:
        for kind in ("skills", "plugins"):
            path = built_in_root / f"{kind}.yml"
            candidates.extend(_load_candidates(path, kind[:-1]))
    if not candidates:
        return []

    query = _query_terms(snapshot, phase, worktree)
    scored = []
    for candidate in candidates:
        score, reason_terms = _score_candidate(candidate, query, phase)
        if score <= 0:
            continue
        scored.append((score, candidate["kind"], candidate["name"], candidate, reason_terms))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    recommendations = [
        _to_recommendation(candidate, score, reason_terms)
        for score, _kind, _name, candidate, reason_terms in scored[:limit]
    ]
    return [
        apply_permission_to_recommendation(worktree, recommendation)
        for recommendation in recommendations
    ]


def render_recommendations(recommendations: list[EcosystemRecommendation]) -> str:
    if not recommendations:
        return "- No skill or plugin recommendations matched this phase."
    return "\n".join(
        (
            f"- {rec.kind}: {rec.name} ({rec.label}) - {rec.reason}"
            + (f" Command hint: `{rec.command_hint}`." if rec.command_hint else "")
            + (" User approval required." if rec.user_approval_required else "")
        )
        for rec in recommendations
    )


def merge_agent_recommendations(
    recommendation_sets: list[AgentRecommendationSet],
    *,
    limit: int = 8,
    worktree: Path | None = None,
) -> EcosystemRecommendationMergeReport:
    """Merge multiple agents' tool recommendations into one coordinator view."""

    grouped: dict[
        tuple[str, str], list[tuple[AgentRecommendationSet, EcosystemRecommendation]]
    ] = {}
    for recommendation_set in recommendation_sets:
        for recommendation in recommendation_set.recommendations:
            if worktree is not None:
                recommendation = apply_permission_to_recommendation(worktree, recommendation)
            key = (recommendation.kind, recommendation.name)
            grouped.setdefault(key, []).append((recommendation_set, recommendation))

    merged = [_merge_group(items) for items in grouped.values()]
    merged.sort(
        key=lambda item: (
            -item.support_count,
            item.user_approval_required,
            -item.confidence,
            item.kind,
            item.name,
        )
    )
    selected = merged[:limit]
    conflicts = _recommendation_conflicts(grouped)
    user_questions = _recommendation_user_questions(selected, conflicts)
    agent_actions = _recommendation_agent_actions(selected, conflicts)
    return EcosystemRecommendationMergeReport(
        summary=(
            f"Merged {sum(len(item.recommendations) for item in recommendation_sets)} "
            f"recommendation(s) from {len(recommendation_sets)} agent(s): "
            f"{len(selected)} selected, {len(conflicts)} conflict(s), "
            f"{len(user_questions)} user-facing question(s)."
        ),
        agent_count=len(recommendation_sets),
        recommendations=selected,
        conflicts=conflicts,
        user_questions=user_questions,
        agent_actions=agent_actions,
    )


def render_recommendation_merge_report(report: EcosystemRecommendationMergeReport) -> str:
    lines = [
        "# Cross-Agent Ecosystem Recommendation Merge",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No tool-routing decision is waiting on the user."]),
        "",
        "## Agent Can Use",
    ]
    if not report.recommendations:
        lines.append("- No merged recommendations.")
    for recommendation in report.recommendations:
        approval = " User approval required." if recommendation.user_approval_required else ""
        lines.append(
            f"- {recommendation.kind}: {recommendation.name} ({recommendation.label}) "
            f"supported by {recommendation.support_count} agent(s). "
            f"{recommendation.reason}{approval}"
        )
        if recommendation.command_hint:
            lines.append(f"  Command hint: `{recommendation.command_hint}`")
    lines.extend(["", "## Conflicts"])
    if not report.conflicts:
        lines.append("- No recommendation conflicts.")
    for conflict in report.conflicts:
        marker = " user" if conflict.needs_user else ""
        lines.append(f"- [{conflict.severity.upper()}{marker}] {conflict.summary}")
        if conflict.options:
            lines.append(f"  Options: {', '.join(conflict.options)}")
    lines.extend(["", "## Agent Actions", _bullets(report.agent_actions or ["No action needed."])])
    return "\n".join(lines) + "\n"


def _merge_group(
    items: list[tuple[AgentRecommendationSet, EcosystemRecommendation]],
) -> MergedEcosystemRecommendation:
    first = items[0][1]
    agent_ids = _dedupe([item[0].agent_id for item in items])
    reasons = _dedupe([_sanitize_text(item[1].reason) for item in items if item[1].reason])
    command_hints = _dedupe(
        [_sanitize_text(item[1].command_hint) for item in items if item[1].command_hint]
    )
    registries = _dedupe([item[1].source_registry for item in items if item[1].source_registry])
    confidence = sum(item[1].confidence for item in items) / len(items)
    user_approval_required = any(item[1].user_approval_required for item in items)
    reason = f"{len(agent_ids)} agent(s) recommended this. " + (
        reasons[0] if reasons else "Matches the current goal context."
    )
    return MergedEcosystemRecommendation(
        kind=first.kind,
        name=first.name,
        label=first.label,
        reason=reason,
        confidence=min(confidence + (0.1 * (len(agent_ids) - 1)), 1.0),
        command_hint=command_hints[0] if len(command_hints) == 1 else "",
        source_registry=registries[0] if registries else first.source_registry,
        user_approval_required=user_approval_required,
        support_count=len(agent_ids),
        agent_ids=agent_ids,
        reasons=reasons,
    )


def _recommendation_conflicts(
    grouped: dict[tuple[str, str], list[tuple[AgentRecommendationSet, EcosystemRecommendation]]],
) -> list[EcosystemRecommendationConflict]:
    conflicts: list[EcosystemRecommendationConflict] = []
    for (kind, name), items in grouped.items():
        agent_ids = _dedupe([item[0].agent_id for item in items])
        command_hints = _dedupe(
            [_sanitize_text(item[1].command_hint) for item in items if item[1].command_hint]
        )
        approval_values = {item[1].user_approval_required for item in items}
        if len(command_hints) > 1:
            conflicts.append(
                EcosystemRecommendationConflict(
                    severity="p2",
                    kind=kind,  # type: ignore[arg-type]
                    name=name,
                    summary=f"Agents disagree on the command hint for {kind} {name}.",
                    agent_ids=agent_ids,
                    options=command_hints,
                    needs_user=False,
                )
            )
        if len(approval_values) > 1:
            conflicts.append(
                EcosystemRecommendationConflict(
                    severity="p1",
                    kind=kind,  # type: ignore[arg-type]
                    name=name,
                    summary=f"Agents disagree on whether {kind} {name} needs approval.",
                    agent_ids=agent_ids,
                    options=["Require approval", "Treat as agent-routine"],
                    needs_user=False,
                )
            )
    return conflicts


def _recommendation_user_questions(
    recommendations: list[MergedEcosystemRecommendation],
    conflicts: list[EcosystemRecommendationConflict],
) -> list[str]:
    questions = [
        f"Approve use of {item.kind} {item.name}?"
        for item in recommendations
        if item.user_approval_required
    ]
    questions.extend(conflict.summary for conflict in conflicts if conflict.needs_user)
    return _dedupe(questions)


def _recommendation_agent_actions(
    recommendations: list[MergedEcosystemRecommendation],
    conflicts: list[EcosystemRecommendationConflict],
) -> list[str]:
    actions = [
        (
            f"Use {item.kind} {item.name} for the next phase; "
            f"{'ask for approval first' if item.user_approval_required else 'record it as agent-selected'}."
        )
        for item in recommendations
    ]
    actions.extend(
        f"Resolve routing conflict without user input: {conflict.summary}"
        for conflict in conflicts
        if not conflict.needs_user
    )
    return _dedupe(actions)


def _sanitize_text(text: str) -> str:
    sanitized = text.replace(str(Path.home()), "~")
    user_root = "/" + "Users" + "/"
    temp_root = "/" + "private" + "/" + "var" + "/" + "folders" + "/"
    sanitized = re.sub(re.escape(user_root) + r"[^/\s]+", "~", sanitized)
    sanitized = re.sub(re.escape(temp_root) + r"[^\s]+", "<temp>", sanitized)
    return sanitized


def _registry_root(worktree: Path) -> Path:
    if (worktree / "registries").exists():
        return worktree / "registries"
    return _built_in_registry_root()


def _built_in_registry_root() -> Path:
    return Path(__file__).resolve().parents[2] / "registries"


def _load_candidates(path: Path, kind: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get(f"{kind}s", {})
    if not isinstance(entries, dict):
        return []
    candidates = []
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        candidates.append(
            {
                "kind": kind,
                "name": str(name),
                "label": str(entry.get("label", name)),
                "description": str(entry.get("description", "")),
                "use_when": _strings(entry.get("use_when", [])),
                "phases": _strings(entry.get("phases", [])),
                "profiles": _strings(entry.get("profiles", [])),
                "command_hint": str(entry.get("command_hint", "")),
                "risk": str(entry.get("risk", "low")),
                "requires_user_approval": bool(entry.get("requires_user_approval", False)),
                "source_registry": path.name,
            }
        )
    return candidates


def _query_terms(snapshot: GoalSnapshot, phase: Phase, worktree: Path) -> set[str]:
    text = " ".join(
        [
            snapshot.objective,
            snapshot.why,
            phase.title,
            phase.goal,
            " ".join(phase.acceptance_criteria),
            " ".join(snapshot.risks),
            " ".join(snapshot.blockers),
        ]
    )
    terms = set(_tokens(text))
    terms.update(_project_signals(worktree))
    if snapshot.decisions:
        terms.update({"decision", "tradeoff", "risk"})
    if snapshot.architecture is not None:
        terms.update({"architecture", "diagram", "map"})
    return terms


def _project_signals(worktree: Path) -> set[str]:
    signals: set[str] = set()
    if (worktree / "pyproject.toml").exists():
        signals.update({"python", "test", "pytest", "ruff"})
    if (worktree / "package.json").exists():
        signals.update({"web", "frontend", "javascript", "typescript", "node"})
    if (worktree / "tests").exists():
        signals.update({"test", "testing"})
    if any(worktree.glob("**/migrations")):
        signals.update({"database", "migration"})
    if (worktree / "README.md").exists() or (worktree / "docs").exists():
        signals.update({"docs", "documentation"})
    return signals


def _score_candidate(
    candidate: dict[str, Any], query: set[str], phase: Phase
) -> tuple[float, list[str]]:
    haystack = set(
        _tokens(
            " ".join(
                [
                    candidate["name"],
                    candidate["label"],
                    candidate["description"],
                    " ".join(candidate["use_when"]),
                    " ".join(candidate["profiles"]),
                ]
            )
        )
    )
    matched = sorted(query & haystack)
    score = float(len(matched))
    phase_matches = sorted(set(candidate["phases"]) & {phase.phase_id.lower(), phase.title.lower()})
    if phase_matches:
        score += 2.0
        matched.extend(phase_matches)
    if "review" in phase.title.lower() and {"review", "quality"} & haystack:
        score += 1.5
        matched.append("review phase")
    if "decision" in query and {"decision", "tradeoff", "risk"} & haystack:
        score += 1.5
        matched.append("decision context")
    if candidate["kind"] == "skill":
        score += 0.2
    return score, _dedupe(matched)


def _to_recommendation(
    candidate: dict[str, Any], score: float, reason_terms: list[str]
) -> EcosystemRecommendation:
    reason = (
        "Matches this goal or phase through " + ", ".join(reason_terms[:5]) + "."
        if reason_terms
        else "Matches the current goal context."
    )
    return EcosystemRecommendation(
        kind=candidate["kind"],
        name=candidate["name"],
        label=candidate["label"],
        reason=reason,
        confidence=min(score / 8.0, 1.0),
        command_hint=candidate["command_hint"],
        source_registry=candidate["source_registry"],
        user_approval_required=candidate["requires_user_approval"] or candidate["risk"] == "high",
    )


def _current_phase(snapshot: GoalSnapshot) -> Phase:
    if snapshot.current_phase is None:
        return snapshot.phases[-1]
    return next(
        (phase for phase in snapshot.phases if phase.phase_id == snapshot.current_phase),
        snapshot.phases[0],
    )


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).lower() for item in value]
    if isinstance(value, str):
        return [value.lower()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
