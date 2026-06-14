from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from goals.models import (
    PersonalizationContext,
    UserMemory,
    UserMemoryEvent,
    UserPreferenceArea,
    UserPreferenceClaim,
    utc_now,
)
from goals.storage import GoalsError, atomic_write_text, lock_file

USER_MEMORY_SCHEMA_VERSION = 1
INTERVIEW_QUESTIONS = [
    "Which decision or tradeoff from this goal matched how you want me to decide next time?",
    "Where should I have asked sooner, decided myself, or explained differently?",
    "What stable preference should Goals remember for future goals?",
]
_ACTIVE_SOURCES = {"manual", "post_goal_interview"}


def goals_home() -> Path:
    configured = os.environ.get("GOALS_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".goals"


def user_memory_dir() -> Path:
    return goals_home() / "user"


def user_events_path() -> Path:
    return user_memory_dir() / "events.jsonl"


def user_memory_path() -> Path:
    return user_memory_dir() / "memory.json"


def read_user_events() -> list[UserMemoryEvent]:
    path = user_events_path()
    if not path.exists():
        return []
    events: list[UserMemoryEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(UserMemoryEvent.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001
            raise GoalsError(f"Invalid user memory event at {path}:{line_number}: {exc}") from exc
    return events


def append_user_event(event: UserMemoryEvent) -> UserMemory:
    path = user_events_path()
    with lock_file(path):
        events = read_user_events()
        if any(existing.event_id == event.event_id for existing in events):
            return save_user_memory(derive_user_memory(events))
        events.append(event)
        atomic_write_text(path, "\n".join(item.model_dump_json() for item in events) + "\n")
        return save_user_memory(derive_user_memory(events))


def load_user_memory() -> UserMemory:
    path = user_memory_path()
    if not path.exists():
        events = read_user_events()
        memory = derive_user_memory(events)
        return save_user_memory(memory) if events else memory
    try:
        return UserMemory.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GoalsError(f"Invalid user memory at {path}: {exc}") from exc


def save_user_memory(memory: UserMemory) -> UserMemory:
    memory.updated_at = utc_now()
    atomic_write_text(user_memory_path(), memory.model_dump_json(indent=2) + "\n")
    return memory


def derive_user_memory(events: list[UserMemoryEvent]) -> UserMemory:
    claims: dict[str, UserPreferenceClaim] = {}
    prompted_goal_ids: list[str] = []
    interviewed_goal_ids: list[str] = []

    for event in events:
        if event.kind == "interview_prompted":
            _append_unique(prompted_goal_ids, event.goal_id)
            continue
        if event.kind == "forget":
            _apply_forget(claims, event.target_claim_id)
            continue
        if event.kind not in {"manual", "interview", "insights", "judgement"}:
            continue
        if event.kind == "interview":
            _append_unique(interviewed_goal_ids, event.goal_id)
        for summary in _claim_statements(event):
            claim_id = _claim_id(event.area, summary)
            existing = claims.get(claim_id)
            if existing is None:
                existing = UserPreferenceClaim(
                    claim_id=claim_id,
                    area=event.area,
                    statement=summary,
                    confidence=0.0,
                    evidence_event_ids=[],
                    status="candidate",
                    updated_at=event.created_at,
                )
                claims[claim_id] = existing
            _append_unique(existing.evidence_event_ids, event.event_id)
            existing.confidence = _claim_confidence(existing, event)
            existing.updated_at = event.created_at
            if event.source in _ACTIVE_SOURCES:
                existing.status = "active"
                _deactivate_conflicts(claims, existing)
            elif existing.status != "active" and len(existing.evidence_event_ids) >= 2:
                existing.status = "active"

    memory = UserMemory(
        schema_version=USER_MEMORY_SCHEMA_VERSION,
        claims=sorted(
            claims.values(),
            key=lambda item: (
                _status_rank(item.status),
                item.area,
                -item.confidence,
                item.statement,
            ),
        ),
        prompted_goal_ids=prompted_goal_ids,
        interviewed_goal_ids=interviewed_goal_ids,
    )
    return memory


def _claim_statements(event: UserMemoryEvent) -> list[str]:
    if event.kind == "interview" and event.details:
        return [
            statement
            for statement in (_clean_statement(detail) for detail in event.details)
            if statement
        ]
    summary = _clean_statement(event.summary)
    return [summary] if summary else []


def build_personalization_context(limit: int = 5) -> PersonalizationContext:
    memory = load_user_memory()
    active = [claim for claim in memory.claims if claim.status == "active"]
    active.sort(key=lambda item: (item.confidence, len(item.evidence_event_ids)), reverse=True)
    selected = active[:limit]
    if not selected:
        return PersonalizationContext(summary="No user preference memory recorded yet.")
    guidance = [
        f"{claim.area}: {claim.statement} ({claim.confidence:.0%})" for claim in selected
    ]
    average = sum(claim.confidence for claim in selected) / len(selected)
    return PersonalizationContext(
        summary="; ".join(guidance),
        claim_ids=[claim.claim_id for claim in selected],
        guidance=guidance,
        confidence=average,
    )


def render_user_memory(memory: UserMemory) -> str:
    lines = [
        "# User Memory",
        "",
        f"Memory file: `{user_memory_path()}`",
        "",
        "## Active Claims",
    ]
    active = [claim for claim in memory.claims if claim.status == "active"]
    candidates = [claim for claim in memory.claims if claim.status == "candidate"]
    inactive = [claim for claim in memory.claims if claim.status in {"inactive", "forgotten"}]
    lines.append(_render_claims(active, "No active user preference claims recorded."))
    lines.extend(["", "## Candidate Claims", _render_claims(candidates, "No candidate claims.")])
    if inactive:
        lines.extend(["", "## Inactive Claims", _render_claims(inactive, "No inactive claims.")])
    return "\n".join(lines).rstrip() + "\n"


def render_personalization_context(context: PersonalizationContext) -> str:
    if not context.guidance:
        return f"- {context.summary}"
    return "\n".join(f"- {item}" for item in context.guidance)


def events_from_insights(text: str, *, area: UserPreferenceArea = "decision") -> list[UserMemoryEvent]:
    statements = _extract_statements(text)
    return [
        UserMemoryEvent(
            kind="insights",
            area=area,
            summary=statement,
            source="claude_insights",
            confidence=0.45,
        )
        for statement in statements
    ]


def record_interview_answers(goal_id: str, answers: list[str]) -> UserMemoryEvent:
    clean_answers = [_clean_statement(answer) for answer in answers if _clean_statement(answer)]
    if len(clean_answers) != 3:
        raise GoalsError("Interview requires exactly three non-empty answers.")
    return UserMemoryEvent(
        kind="interview",
        area="decision",
        summary=" | ".join(clean_answers),
        source="post_goal_interview",
        goal_id=goal_id,
        confidence=0.9,
        details=clean_answers,
    )


def mark_interview_prompted(goal_id: str) -> bool:
    if not goal_id:
        return False
    memory = load_user_memory()
    if goal_id in memory.prompted_goal_ids or goal_id in memory.interviewed_goal_ids:
        return False
    append_user_event(
        UserMemoryEvent(
            kind="interview_prompted",
            source="system",
            goal_id=goal_id,
            summary="Post-goal interview was shown.",
        )
    )
    return True


def render_post_goal_interview(goal_id: str) -> str:
    questions = "\n".join(f"{index}. {question}" for index, question in enumerate(INTERVIEW_QUESTIONS, 1))
    return (
        "\nPost-goal personalization interview:\n"
        f"{questions}\n\n"
        "Record answers with:\n"
        f'goals user interview --goal {goal_id} --answer "..." --answer "..." --answer "..."\n'
    )


def forget_claim(target: str, *, purge: bool = False) -> UserMemory:
    if purge and target == "--all":
        for path in (user_events_path(), user_memory_path()):
            path.unlink(missing_ok=True)
        return UserMemory()
    return append_user_event(
        UserMemoryEvent(
            kind="forget",
            source="manual",
            target_claim_id="*" if target == "--all" else target,
            summary=f"Forget {target}",
        )
    )


def _extract_statements(text: str) -> list[str]:
    statements: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw).strip()
        if len(line) < 8:
            continue
        statement = _clean_statement(line)
        key = statement.lower()
        if key in seen:
            continue
        seen.add(key)
        statements.append(statement)
        if len(statements) >= 8:
            break
    if not statements and text.strip():
        statements.append(_clean_statement(text.strip()[:320]))
    return [statement for statement in statements if statement]


def _clean_statement(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _claim_id(area: str, statement: str) -> str:
    digest = hashlib.sha1(f"{area}\0{statement.lower()}".encode("utf-8")).hexdigest()[:10]
    return f"UPC-{digest}"


def _claim_confidence(claim: UserPreferenceClaim, event: UserMemoryEvent) -> float:
    base = max(claim.confidence, max(0.0, min(1.0, event.confidence)))
    bonus = 0.08 * max(0, len(claim.evidence_event_ids) - 1)
    if event.source in _ACTIVE_SOURCES:
        bonus += 0.05
    return min(0.98, base + bonus)


def _deactivate_conflicts(
    claims: dict[str, UserPreferenceClaim], active_claim: UserPreferenceClaim
) -> None:
    for claim in claims.values():
        if (
            claim.claim_id != active_claim.claim_id
            and claim.area == active_claim.area
            and claim.status == "active"
            and _claims_conflict(claim.statement, active_claim.statement)
        ):
            claim.status = "inactive"


def _claims_conflict(left: str, right: str) -> bool:
    left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
    right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
    opposite_pairs = (
        ("fast", "ask"),
        ("fast", "asking"),
        ("quick", "ask"),
        ("quick", "asking"),
        ("decide", "ask"),
        ("decide", "asking"),
        ("auto", "ask"),
        ("auto", "asking"),
        ("concise", "detailed"),
        ("brief", "detailed"),
        ("technical", "plain"),
    )
    for a, b in opposite_pairs:
        if (a in left_tokens and b in right_tokens) or (b in left_tokens and a in right_tokens):
            return True
    return False


def _apply_forget(claims: dict[str, UserPreferenceClaim], target: str) -> None:
    if target == "*":
        for claim in claims.values():
            claim.status = "forgotten"
        return
    if target in claims:
        claims[target].status = "forgotten"


def _status_rank(status: str) -> int:
    return {"active": 0, "candidate": 1, "inactive": 2, "forgotten": 3}.get(status, 4)


def _render_claims(claims: list[UserPreferenceClaim], empty: str) -> str:
    if not claims:
        return f"- {empty}"
    return "\n".join(
        f"- `{claim.claim_id}` [{claim.area}/{claim.status}] {claim.statement} "
        f"({claim.confidence:.0%}, {len(claim.evidence_event_ids)} evidence ref(s))"
        for claim in claims
    )


def _append_unique(items: list[str], item: str) -> None:
    if item and item not in items:
        items.append(item)
