from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from goals.models import EcosystemRecommendation, GoalSnapshot, Phase

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
    return [
        _to_recommendation(candidate, score, reason_terms)
        for score, _kind, _name, candidate, reason_terms in scored[:limit]
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
