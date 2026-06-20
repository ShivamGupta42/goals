from __future__ import annotations

import re
from typing import Literal

from goals.models import (
    CapabilityCheckReport,
    CapabilityGap,
    CapabilityMatch,
    CapabilityNeed,
    GoalSnapshot,
)
from goals.skill_discovery import DiscoveredSkill, discover_skills

CapabilityAdapter = Literal["auto", "claude", "codex"]

_CATEGORIES = {
    "approval",
    "browser",
    "data",
    "external_service",
    "other",
    "skill",
    "tool",
}
_BROWSER_TERMS = {
    "browser",
    "chromium",
    "css",
    "dom",
    "frontend",
    "html",
    "playwright",
    "screenshot",
    "ui",
    "visual",
    "webpage",
    "website",
}
_BROWSER_SKILL_HINTS = {
    "browser",
    "chrome",
    "control-in-app-browser",
    "control-chrome",
    "frontend-testing",
    "playwright",
}
_EXPLICIT_SKILL_RE = re.compile(r"\bskill:([A-Za-z0-9_.:-]+)")
_EXPLICIT_CAPABILITY_RE = re.compile(r"\bcapability:([A-Za-z_]+)(?::([^\n;]+))?", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def analyze_capabilities(
    snapshot: GoalSnapshot,
    *,
    adapter: CapabilityAdapter = "auto",
    explicit_needs: list[str] | None = None,
    skills: list[DiscoveredSkill] | None = None,
) -> CapabilityCheckReport:
    """Compare goal/phase capability needs with the live skill inventory."""
    if adapter not in {"auto", "claude", "codex"}:
        raise ValueError("adapter must be auto, claude, or codex.")
    inventory = skills if skills is not None else discover_skills()
    needs = _dedupe_needs(
        [
            *derive_capability_needs(snapshot),
            *[parse_need_spec(spec, snapshot) for spec in (explicit_needs or [])],
        ]
    )
    gaps = [_evaluate_need(need, inventory, adapter) for need in needs]
    actionable = [gap for gap in gaps if gap.status != "available"]
    required_open = [gap for gap in actionable if gap.required]
    user_questions = [gap.suggested_action for gap in actionable if gap.needs_user]
    agent_actions = [
        gap.suggested_action
        for gap in actionable
        if gap.suggested_action and not gap.needs_user
    ]
    if not needs:
        summary = "No capability needs detected for the current goal."
    elif not actionable:
        summary = f"All {len(needs)} detected capability need(s) are available."
    else:
        summary = (
            f"Found {len(actionable)} capability gap(s): "
            f"{len(required_open)} required, {len(actionable) - len(required_open)} optional."
        )
    return CapabilityCheckReport(
        goal_id=snapshot.goal_id,
        adapter=adapter,
        passed=not required_open,
        summary=summary,
        needs=needs,
        gaps=actionable,
        user_questions=_dedupe_text(user_questions),
        agent_actions=_dedupe_text(agent_actions),
    )


def derive_capability_needs(snapshot: GoalSnapshot) -> list[CapabilityNeed]:
    needs: list[CapabilityNeed] = []
    global_text = " ".join([snapshot.objective, snapshot.why, " ".join(snapshot.definition_of_done)])
    phase_texts: list[tuple[str | None, str, list[str]]] = [(None, global_text, [])]
    for phase in snapshot.phases:
        evidence_refs = [f"phase:{phase.phase_id}"]
        bits = [phase.title, phase.goal, " ".join(phase.acceptance_criteria)]
        if phase.evidence is not None:
            bits.extend(phase.evidence.known_gaps)
            bits.extend(phase.evidence.ambiguous)
        phase_texts.append((phase.phase_id, " ".join(bits), evidence_refs))

    for phase_id, text, refs in phase_texts:
        if _looks_like_browser_need(text):
            needs.append(
                CapabilityNeed(
                    need_id=_need_id("browser", "browser-ui-verification", phase_id),
                    title="Browser/UI verification",
                    category="browser",
                    required=True,
                    phase_id=phase_id,
                    query="browser visual DOM screenshot Playwright",
                    reason="The goal or phase mentions browser, visual, UI, DOM, or web testing work.",
                    preferred_agents=[],
                    evidence_refs=refs,
                )
            )
        for skill_name in _EXPLICIT_SKILL_RE.findall(text):
            needs.append(
                CapabilityNeed(
                    need_id=_need_id("skill", skill_name, phase_id),
                    title=f"Skill: {skill_name}",
                    category="skill",
                    required=True,
                    phase_id=phase_id,
                    query=skill_name,
                    reason="Explicit skill requirement recorded in the goal text or evidence gaps.",
                    evidence_refs=refs,
                )
            )
        for category, query in _EXPLICIT_CAPABILITY_RE.findall(text):
            parsed_category = category.lower()
            if parsed_category not in _CATEGORIES:
                parsed_category = "other"
            label = (query or category).strip()
            needs.append(
                CapabilityNeed(
                    need_id=_need_id(parsed_category, label or parsed_category, phase_id),
                    title=_title_for(parsed_category, label or parsed_category),
                    category=parsed_category,  # type: ignore[arg-type]
                    required=True,
                    phase_id=phase_id,
                    query=label,
                    reason="Explicit capability requirement recorded in the goal text or evidence gaps.",
                    evidence_refs=refs,
                )
            )
    return needs


def parse_need_spec(spec: str, snapshot: GoalSnapshot) -> CapabilityNeed:
    raw = spec.strip()
    if not raw:
        raise ValueError("Capability need cannot be empty.")
    required = True
    if raw.lower().startswith("optional:"):
        required = False
        raw = raw.split(":", 1)[1].strip()
    if ":" in raw:
        category, query = raw.split(":", 1)
        category = category.strip().lower()
        query = query.strip()
    else:
        category, query = "other", raw
    if category not in _CATEGORIES:
        query = raw
        category = "other"
    phase_id = snapshot.current_phase
    return CapabilityNeed(
        need_id=_need_id(category, query, phase_id),
        title=_title_for(category, query),
        category=category,  # type: ignore[arg-type]
        required=required,
        phase_id=phase_id,
        query=query,
        reason="Explicit need supplied to `goals capability check`.",
        evidence_refs=[f"phase:{phase_id}"] if phase_id else [],
    )


def render_capability_report(report: CapabilityCheckReport) -> str:
    lines = [
        "# Capability Check",
        "",
        f"Goal: {report.goal_id}",
        f"Adapter: {report.adapter}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs",
    ]
    if not report.needs:
        lines.append("- No capability needs detected.")
    for need in report.needs:
        required = "required" if need.required else "optional"
        phase = f" phase={need.phase_id}" if need.phase_id else ""
        lines.append(f"- [{need.category}][{required}{phase}] {need.title}")
        if need.reason:
            lines.append(f"  Reason: {need.reason}")
    lines.extend(["", "## Gaps"])
    if not report.gaps:
        lines.append("- No capability gaps found.")
    for gap in report.gaps:
        user = " user" if gap.needs_user else ""
        lines.append(f"- [{gap.severity.upper()}][{gap.status}{user}] {gap.title}")
        if gap.detail:
            lines.append(f"  Detail: {gap.detail}")
        if gap.suggested_action:
            lines.append(f"  Next: {gap.suggested_action}")
    lines.extend(["", "## Needs The User"])
    lines.append(_bullets(report.user_questions or ["No capability question is waiting."]))
    lines.extend(["", "## Agent Can Do"])
    lines.append(_bullets(report.agent_actions or ["No capability setup action is suggested."]))
    return "\n".join(lines) + "\n"


def _evaluate_need(
    need: CapabilityNeed,
    skills: list[DiscoveredSkill],
    adapter: CapabilityAdapter,
) -> CapabilityGap:
    matches = [_match_for(skill) for skill in skills if _skill_matches_need(skill, need)]
    if _has_available_match(matches, adapter):
        return CapabilityGap(
            need_id=need.need_id,
            title=need.title,
            category=need.category,
            severity="p2" if not need.required else "p1",
            status="available",
            required=need.required,
            detail="Capability is available in the live skill inventory.",
            matches=matches,
            evidence_refs=need.evidence_refs,
        )
    severity = "p1" if need.required else "p2"
    if matches and any("bundled" in match.sources for match in matches):
        target = "codex" if adapter == "auto" else adapter
        return CapabilityGap(
            need_id=need.need_id,
            title=need.title,
            category=need.category,
            severity=severity,
            status="needs_install",
            required=need.required,
            detail=_match_detail(matches, adapter),
            suggested_action=f"Run `goals skills install --target {target}` or choose an installed equivalent.",
            matches=matches,
            evidence_refs=need.evidence_refs,
        )
    if matches:
        target = "the active agent" if adapter == "auto" else adapter
        return CapabilityGap(
            need_id=need.need_id,
            title=need.title,
            category=need.category,
            severity=severity,
            status="missing_for_agent",
            required=need.required,
            needs_user=adapter != "auto",
            detail=_match_detail(matches, adapter),
            suggested_action=(
                f"Install or approve this capability for {target}, or switch to an agent "
                "where the matched skill is already installed."
            ),
            matches=matches,
            evidence_refs=need.evidence_refs,
        )
    return CapabilityGap(
        need_id=need.need_id,
        title=need.title,
        category=need.category,
        severity=severity,
        status="missing",
        required=need.required,
        needs_user=need.required,
        detail=(
            f"No discovered skill matched `{need.query or need.title}`. "
            "Goals will not guess that a missing external skill or tool is safe."
        ),
        suggested_action=(
            "Ask the user to approve a trusted skill/plugin source, provide an existing "
            "tooling path, or explicitly accept a local fallback."
        ),
        evidence_refs=need.evidence_refs,
    )


def _has_available_match(matches: list[CapabilityMatch], adapter: CapabilityAdapter) -> bool:
    if adapter == "auto":
        return any(match.agents for match in matches)
    return any(adapter in match.agents for match in matches)


def _skill_matches_need(skill: DiscoveredSkill, need: CapabilityNeed) -> bool:
    if need.category == "browser":
        return _skill_matches_browser(skill) or _text_matches(skill, need.query)
    if need.category == "skill":
        return _normalize(skill.name) == _normalize(need.query)
    return _text_matches(skill, need.query or need.title)


def _skill_matches_browser(skill: DiscoveredSkill) -> bool:
    haystack = f"{skill.name} {skill.description}".lower()
    return any(hint in haystack for hint in _BROWSER_SKILL_HINTS)


def _text_matches(skill: DiscoveredSkill, query: str) -> bool:
    tokens = set(_tokens(query))
    if not tokens:
        return False
    haystack = set(_tokens(f"{skill.name} {skill.description}"))
    return bool(tokens & haystack)


def _looks_like_browser_need(text: str) -> bool:
    tokens = set(_tokens(text))
    return bool(tokens & _BROWSER_TERMS)


def _match_for(skill: DiscoveredSkill) -> CapabilityMatch:
    return CapabilityMatch(
        name=skill.name,
        sources=list(skill.sources),
        agents=list(skill.agents),
        path=skill.path,
    )


def _match_detail(matches: list[CapabilityMatch], adapter: CapabilityAdapter) -> str:
    parts = []
    for match in matches:
        agents = ", ".join(match.agents) if match.agents else "not installed"
        sources = ", ".join(match.sources)
        parts.append(f"{match.name} [{agents}; sources: {sources}]")
    adapter_text = "" if adapter == "auto" else f" for adapter `{adapter}`"
    return f"Matched skill(s){adapter_text}: " + "; ".join(parts)


def _title_for(category: str, query: str) -> str:
    label = query.strip() or category
    if category == "skill":
        return f"Skill: {label}"
    if category == "browser":
        return "Browser/UI verification" if label == "browser" else f"Browser/UI: {label}"
    return f"{category.replace('_', ' ').title()}: {label}"


def _need_id(category: str, query: str, phase_id: str | None) -> str:
    suffix = _slug(query or category)
    prefix = f"{phase_id.lower()}-" if phase_id else ""
    return f"{prefix}{category}-{suffix}"


def _dedupe_needs(needs: list[CapabilityNeed]) -> list[CapabilityNeed]:
    seen: set[str] = set()
    unique: list[CapabilityNeed] = []
    for need in needs:
        if need.need_id in seen:
            continue
        seen.add(need.need_id)
        unique.append(need)
    return unique


def _dedupe_text(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _normalize(text: str) -> str:
    return "-".join(_tokens(text))


def _slug(text: str) -> str:
    value = _normalize(text)
    return value[:48] or "need"
