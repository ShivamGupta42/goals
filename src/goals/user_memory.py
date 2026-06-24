"""Goal-execution memory: small, private, and human-editable.

Two plain-Markdown files under ``~/.goals/user/`` — both yours to read and edit:

- ``preferences.md`` — durable preferences that steer how Goals auto-executes.
  You own it. Goals only adds to it when you state or confirm a preference;
  it never rewrites your edits.
- ``observations.md`` — an append-only log of situated decisions Goals saw you
  make while a goal ran: *what* you chose and the *context*, never an invented
  reason. ``you said:`` is your own words; ``note:`` is recorded rationale.

Design choices (see docs/GOAL_EXECUTION_MEMORY.md):
- No causal attribution. We record context + choice, not "chose X *because* Y".
  People confabulate reasons, so an inferred cause would be fabricated.
- No silent generalization. An observation is scoped to its goal. It only
  becomes a standing preference when you state/confirm it, or after a pattern
  recurs across goals and you promote it.
- Markdown, not JSON, because you must be able to edit it by hand.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from goals.models import (
    AutonomySignals,
    JudgementObservation,
    PersonalizationContext,
    Preference,
    UserMemory,
    UserPreferenceArea,
    utc_now,
)
from goals.storage import GoalsError, atomic_write_text, lock_file

INTERVIEW_QUESTIONS = [
    "Which decision from this goal reflects how you'd want me to decide next time?",
    "Where should I have asked sooner, decided myself, or explained differently?",
    "What stable preference should Goals remember for future goals?",
]

_AREAS: tuple[str, ...] = ("risk", "communication", "workflow", "technical", "decision", "other")
_MIDDOT = "·"

_PREFERENCES_HEADER = (
    "# Your Goals preferences\n"
    "<!-- Goals reads this to decide how to execute your goals. It's yours: "
    "edit, reorder, or delete any line. -->\n"
    "<!-- One preference per bullet under an area heading "
    "(risk, communication, workflow, technical, decision, other). -->\n"
)
_OBSERVATIONS_HEADER = (
    "# Goals observations (append-only)\n"
    "<!-- Goals appends one decision as you work: a `chose:` line, plus optional "
    "`when:` (context) and a note. Never an invented reason. -->\n"
    "<!-- `you said:` is your own words; `note:` is recorded rationale. Edit a "
    "line only to correct it. -->\n"
)


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def goals_home() -> Path:
    configured = os.environ.get("GOALS_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".goals"


def user_memory_dir() -> Path:
    return goals_home() / "user"


def preferences_path() -> Path:
    return user_memory_dir() / "preferences.md"


def observations_path() -> Path:
    return user_memory_dir() / "observations.md"


# --------------------------------------------------------------------------- #
# Preferences (durable, user-owned)
# --------------------------------------------------------------------------- #
def load_preferences() -> list[Preference]:
    _maybe_migrate_legacy()
    path = preferences_path()
    if not path.exists():
        return []
    preferences: list[Preference] = []
    area: UserPreferenceArea = "other"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        heading = re.match(r"^##\s+(.*)$", line)
        if heading:
            candidate = heading.group(1).strip().lower()
            area = candidate if candidate in _AREAS else "other"  # type: ignore[assignment]
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if bullet:
            text = _clean(bullet.group(1))
            if text:
                preferences.append(Preference(area=area, text=text))
    return preferences


def add_preference(area: str, text: str) -> Preference:
    """Append a preference under its area heading, preserving all other content."""
    preference = Preference(area=_validate_area(area), text=_clean(text))
    if not preference.text:
        raise GoalsError("A preference needs some text.")
    path = preferences_path()
    with lock_file(path):
        if any(
            existing.area == preference.area and existing.text.lower() == preference.text.lower()
            for existing in load_preferences()
        ):
            return preference
        lines = _read_lines(path, _PREFERENCES_HEADER)
        _insert_preference_line(lines, preference)
        atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
    return preference


def forget_preference(target: str, *, purge: bool = False) -> list[str]:
    """Remove preference bullets matching ``target`` (substring, case-insensitive).

    ``target == '--all'`` clears every preference; with ``purge`` it deletes the
    files outright. Returns the text of every preference removed, so the caller
    can show exactly what was dropped (a substring can match more than one).
    """
    if target == "--all":
        removed_all = [pref.text for pref in load_preferences()]
        if purge:
            for path in (preferences_path(), observations_path()):
                path.unlink(missing_ok=True)
            return removed_all
        path = preferences_path()
        with lock_file(path):
            atomic_write_text(path, _PREFERENCES_HEADER)
        return removed_all
    needle = _clean(target).lower()
    if not needle:
        raise GoalsError("Provide preference text to forget, or use --all.")
    path = preferences_path()
    with lock_file(path):
        if not path.exists():
            return []
        kept: list[str] = []
        removed: list[str] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            bullet = re.match(r"^[-*]\s+(.*)$", raw.strip())
            if bullet and needle in bullet.group(1).lower():
                removed.append(_clean(bullet.group(1)))
                continue
            kept.append(raw)
        if removed:
            atomic_write_text(path, "\n".join(kept).rstrip() + "\n")
    return removed


# --------------------------------------------------------------------------- #
# Observations (episodic, append-only, agent-owned)
# --------------------------------------------------------------------------- #
def record_observation(
    *,
    goal_id: str,
    choice: str,
    context: str = "",
    note: str = "",
    area: str = "decision",
    stated: bool = False,
    reversible: bool | None = None,
    phase_id: str = "",
) -> JudgementObservation:
    """Append one situated observation to the log.

    ``note`` is a free-form annotation. ``stated=True`` means the note is the
    user's *own words* (rendered as ``you said: …``). By default a note is
    treated as recorded rationale, not a user quote — we never claim the user
    said something they may not have. ``reversible``/``phase_id`` are conditioning
    metadata used by autonomy and cross-goal learning.
    """
    clean_note = _clean(note)
    observation = JudgementObservation(
        goal_id=_slug(goal_id),
        area=_validate_area(area),
        choice=_clean(choice),
        context=_clean(context),
        note=clean_note,
        provenance="stated" if (clean_note and stated) else "observed",
        reversible=reversible,
        phase_id=_clean(phase_id),
        created_at=utc_now()[:10],
    )
    if not observation.choice:
        raise GoalsError("An observation needs a choice.")
    path = observations_path()
    with lock_file(path):
        lines = _read_lines(path, _OBSERVATIONS_HEADER)
        lines.extend(_format_observation_block(observation))
        atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
    return observation


def load_observations() -> list[JudgementObservation]:
    _maybe_migrate_legacy()
    path = observations_path()
    if not path.exists():
        return []
    observations: list[JudgementObservation] = []
    current: JudgementObservation | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        parent = _OBS_PARENT_RE.match(raw)
        if parent:
            current = _observation_from_parent(parent)
            observations.append(current)
            continue
        field = _OBS_FIELD_RE.match(raw)
        if field and current is not None:
            key = field.group("key")
            value = _clean(field.group("value"))
            if key == "when":
                current.context = value
            elif key == "reversible":
                current.reversible = value.lower() in {"yes", "true", "y"}
            elif key == "phase":
                current.phase_id = value
            else:  # "note" or "you said"
                current.note = value
                current.provenance = "stated" if key == "you said" else "observed"
        # Anything else (markers, blanks, header, stray human text) is ignored.
    return observations


def unreadable_observation_lines() -> list[str]:
    """Non-blank log lines that aren't a recognizable observation, marker, or header.

    The log is structured, so a hand-edit that breaks the shape would otherwise be
    dropped silently. Surfacing these lets `goals user show` warn instead of losing
    data quietly.
    """
    path = observations_path()
    if not path.exists():
        return []
    bad: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        if _OBS_PARENT_RE.match(raw) or _OBS_FIELD_RE.match(raw):
            continue
        bad.append(stripped)
    return bad


# --------------------------------------------------------------------------- #
# Aggregate / rendering
# --------------------------------------------------------------------------- #
def load_user_memory() -> UserMemory:
    return UserMemory(preferences=load_preferences(), observations=load_observations())


def render_user_memory(memory: UserMemory | None = None) -> str:
    memory = memory or load_user_memory()
    lines = [
        "# User Memory",
        "",
        f"Preferences: `{preferences_path()}` (yours to edit)",
        f"Observations: `{observations_path()}` (append-only log)",
        "",
        "## Standing preferences",
    ]
    if memory.preferences:
        for area in _AREAS:
            in_area = [pref for pref in memory.preferences if pref.area == area]
            if in_area:
                lines.append(f"- [{area}] " + "; ".join(pref.text for pref in in_area))
    else:
        lines.append("- None yet. Add one with `goals user record \"...\"`.")
    recent = memory.observations[-5:]
    lines.extend(["", "## Recent observations"])
    if recent:
        lines.extend(f"- {_describe_observation(obs)}" for obs in recent)
    else:
        lines.append("- None yet.")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Personalization (only confirmed preferences steer auto-execution)
# --------------------------------------------------------------------------- #
def build_personalization_context(limit: int = 5) -> PersonalizationContext:
    preferences = load_preferences()
    if not preferences:
        return PersonalizationContext(summary="No user preference memory recorded yet.")
    selected = preferences[:limit]
    guidance = [f"{pref.area}: {pref.text}" for pref in selected]
    return PersonalizationContext(
        summary="; ".join(guidance),
        guidance=guidance,
        confidence=0.9,
        autonomy=autonomy_signals(preferences),
    )


# Words that turn a preference into an ask-vs-act signal. A preference tightens
# the gate only when it pairs an "ask" intent with a risk/irreversibility target.
_ASK_WORDS = ("ask", "confirm", "check with", "approve", "permission", "run it by", "don't decide")
_DECIDE_WORDS = ("decide", "go ahead", "proceed", "handle", "yourself", "autonomous", "don't ask", "auto")
_IRREVERSIBLE_WORDS = (
    "irreversible", "not reversible", "can't undo", "cannot undo", "permanent",
    "destructive", "delete", "drop", "production", "prod ",
)
_RISK_WORDS = ("risk", "risky", "dangerous", "high-stakes", "high stakes", "sensitive", "unsafe")
_REVERSIBLE_WORDS = ("reversible", "undo", "safe", "low-risk", "low risk", "routine", "small")


def autonomy_signals(preferences: list[Preference] | None = None) -> AutonomySignals:
    """Derive ask-vs-act modulation from confirmed preferences (tighten/relax only)."""
    preferences = load_preferences() if preferences is None else preferences
    confirm_irreversible = confirm_risky = autonomous = False
    sources: list[str] = []
    for pref in preferences:
        low = pref.text.lower()
        asks = any(word in low for word in _ASK_WORDS)
        decides = any(word in low for word in _DECIDE_WORDS)
        if asks and any(word in low for word in _IRREVERSIBLE_WORDS):
            confirm_irreversible = True
            _append_unique(sources, pref.text)
        if asks and any(word in low for word in _RISK_WORDS):
            confirm_risky = True
            _append_unique(sources, pref.text)
        if decides and any(word in low for word in _REVERSIBLE_WORDS):
            autonomous = True
            _append_unique(sources, pref.text)
    return AutonomySignals(
        confirm_irreversible=confirm_irreversible,
        confirm_risky=confirm_risky,
        autonomous_when_reversible=autonomous,
        sources=sources,
    )


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def render_personalization_context(context: PersonalizationContext) -> str:
    if not context.guidance:
        return f"- {context.summary}"
    return "\n".join(f"- {item}" for item in context.guidance)


# --------------------------------------------------------------------------- #
# Goal-end digest (reflect back what was learned, scoped honestly)
# --------------------------------------------------------------------------- #
def build_goal_memory_digest(goal_id: str, *, limit: int = 5) -> str:
    """Plain-language reflection surfaced at goal end.

    Shows the decisions seen in *this* goal (with their context, and your note
    if you gave one), any pattern that has recurred across goals and could
    become a standing preference, and the standing preferences currently in
    effect. Nothing is generalized without your say-so.
    """
    slug = _slug(goal_id)
    observations = load_observations()
    here = [obs for obs in observations if obs.goal_id == slug]
    preferences = load_preferences()
    candidates = _recurring_candidates(observations, preferences)
    if not here and not preferences and not candidates:
        return ""
    lines = ["", "Goal-execution memory — what I noticed:"]
    if here:
        lines.extend(["", "In this goal you decided (kept with its context, scoped to this goal):"])
        lines.extend(f"- {_describe_observation(obs)}" for obs in here[-limit:])
    if candidates:
        lines.extend(["", "Seen across several goals — promote to a standing preference?"])
        for choice, area, count in candidates[:limit]:
            lines.append(
                f'- {area}: "{choice}" ({count} goals). '
                f'Confirm with `goals user record "{choice}" --area {area}`.'
            )
    if preferences:
        lines.extend(["", "Standing preferences I'll apply to future goals (you set these):"])
        lines.extend(f"- {pref.area}: {pref.text}" for pref in preferences[:limit])
    elif here:
        lines.extend(
            [
                "",
                "I won't turn the choices above into standing rules on my own — a choice "
                "made for one goal can be wrong for the next. Set any that should always "
                "hold with `goals user record \"...\"` or the post-goal interview.",
            ]
        )
    lines.extend(
        [
            "",
            f"It's all editable Markdown: `{preferences_path()}` (yours) and "
            f"`{observations_path()}` (the log).",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------- #
# Post-goal interview (answers become stated preferences)
# --------------------------------------------------------------------------- #
def record_interview_answers(goal_id: str, answers: list[str]) -> list[Preference]:
    clean = [_clean(answer) for answer in answers if _clean(answer)]
    if len(clean) != 3:
        raise GoalsError("Interview requires exactly three non-empty answers.")
    # Infer the area from each answer's content rather than its position — the
    # questions don't map cleanly onto areas, so a positional guess mislabels.
    preferences = [add_preference(infer_area(text), text) for text in clean]
    _append_marker("interviewed", _slug(goal_id))
    return preferences


def mark_interview_prompted(goal_id: str) -> bool:
    slug = _slug(goal_id)
    if not slug:
        return False
    if _has_marker(slug, ("prompted", "interviewed")):
        return False
    _append_marker("prompted", slug)
    return True


def render_post_goal_interview(goal_id: str) -> str:
    questions = "\n".join(
        f"{index}. {question}" for index, question in enumerate(INTERVIEW_QUESTIONS, 1)
    )
    return (
        "\nPost-goal personalization interview (answers become editable preferences):\n"
        f"{questions}\n\n"
        "Record answers with:\n"
        f'goals user interview --goal {goal_id} --answer "..." --answer "..." --answer "..."\n'
    )


# --------------------------------------------------------------------------- #
# Claude /insights import (user-curated -> stated preferences)
# --------------------------------------------------------------------------- #
def preferences_from_insights(text: str, *, area: str = "decision") -> list[str]:
    validated = _validate_area(area)
    added: list[str] = []
    for statement in _extract_statements(text):
        added.append(add_preference(validated, statement).text)
    return added


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _read_lines(path: Path, header: str) -> list[str]:
    if path.exists():
        return path.read_text(encoding="utf-8").splitlines()
    return header.rstrip("\n").splitlines()


def _insert_preference_line(lines: list[str], preference: Preference) -> None:
    heading = f"## {preference.area}"
    bullet = f"- {preference.text}"
    for index, raw in enumerate(lines):
        if raw.strip().lower() == heading.lower():
            insert_at = index + 1
            while insert_at < len(lines) and not re.match(r"^##\s+", lines[insert_at].strip()):
                insert_at += 1
            lines.insert(insert_at, bullet)
            return
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(heading)
    lines.append(bullet)


# A self-delimiting Markdown block. Each free-form value (choice / context /
# note) is the entire rest of its own line, so it can contain ANY character —
# the field separators (·, —, quotes, the literal "you said:") can appear in
# user text without corrupting the parse. The structured prefix fields (date,
# goal slug, area) cannot contain their own terminators by construction.
#
#   - 2026-06-24 · goal:add-auth · [risk] · chose: a local file over a database
#     - when: throwaway prototype
#     - you said: no server to manage
def _format_observation_block(observation: JudgementObservation) -> list[str]:
    date = observation.created_at[:10]
    goal = observation.goal_id or "none"
    lines = [
        f"- {date} {_MIDDOT} goal:{goal} {_MIDDOT} "
        f"[{observation.area}] {_MIDDOT} chose: {observation.choice}"
    ]
    if observation.context:
        lines.append(f"  - when: {observation.context}")
    if observation.reversible is not None:
        lines.append(f"  - reversible: {'yes' if observation.reversible else 'no'}")
    if observation.phase_id:
        lines.append(f"  - phase: {observation.phase_id}")
    if observation.note:
        key = "you said" if observation.provenance == "stated" else "note"
        lines.append(f"  - {key}: {observation.note}")
    return lines


_OBS_PARENT_RE = re.compile(
    r"^-\s+(?P<date>\d{4}-\d{2}-\d{2})\s+[·-]\s+goal:(?P<goal>\S*)\s+[·-]\s+"
    r"\[(?P<area>[^\]]+)\]\s+[·-]\s+chose:\s+(?P<choice>.*)$"
)
_OBS_FIELD_RE = re.compile(
    r"^\s+-\s+(?P<key>when|note|you said|reversible|phase):\s*(?P<value>.*)$"
)


def _observation_from_parent(match: re.Match[str]) -> JudgementObservation:
    area = match.group("area").strip().lower()
    goal = match.group("goal")
    return JudgementObservation(
        goal_id="" if goal == "none" else goal,
        area=area if area in _AREAS else "other",  # type: ignore[arg-type]
        choice=_clean(match.group("choice")),
        created_at=match.group("date"),
    )


def _describe_observation(observation: JudgementObservation) -> str:
    text = f"chose {observation.choice}"
    if observation.reversible is False:
        text += " (irreversible)"
    if observation.context:
        text += f" — when {observation.context}"
    if observation.note:
        label = "you said" if observation.provenance == "stated" else "note"
        text += f' ({label}: "{observation.note}")'
    if observation.goal_id:
        text += f" [goal:{observation.goal_id}]"
    return text


def _normalize_choice(text: str) -> str:
    """Loose key so near-identical free-text choices group together.

    Lowercase, drop punctuation, collapse whitespace. This is best-effort: it
    catches "use SQLite" vs "Use SQLite." but not paraphrases. The reliable path
    to a standing preference remains the interview / `goals user record`.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _recurring_candidates(
    observations: list[JudgementObservation],
    preferences: list[Preference],
) -> list[tuple[str, str, int]]:
    """Choices made in >= 2 distinct goals that aren't already a preference."""
    seen: dict[tuple[str, str], set[str]] = {}
    display: dict[tuple[str, str], str] = {}
    for obs in observations:
        if not obs.choice or not obs.goal_id:
            continue
        key = (obs.area, _normalize_choice(obs.choice))
        if not key[1]:
            continue
        seen.setdefault(key, set()).add(obs.goal_id)
        display.setdefault(key, obs.choice)  # keep the first original wording
    covered_pref_text = [_normalize_choice(pref.text) for pref in preferences]

    def _is_covered(area: str, normalized_choice: str) -> bool:
        # A candidate is covered if its normalized choice appears in ANY confirmed
        # preference's text — area-agnostic. This stops the digest from offering to
        # promote a choice the user already turned into a preference, even when they
        # reworded it or filed it under a different area than the suggested command.
        return any(normalized_choice in pref_text for pref_text in covered_pref_text)

    candidates = [
        (display[key], key[0], len(goals))
        for key, goals in seen.items()
        if len(goals) >= 2 and not _is_covered(key[0], key[1])
    ]
    candidates.sort(key=lambda item: item[2], reverse=True)
    return candidates


# --------------------------------------------------------------------------- #
# One-time migration from the legacy JSON store (pre-Markdown).
# --------------------------------------------------------------------------- #
_MIGRATING = False


def _legacy_paths() -> tuple[Path, Path]:
    directory = user_memory_dir()
    return directory / "memory.json", directory / "events.jsonl"


def _maybe_migrate_legacy() -> None:
    """Best-effort import of a pre-Markdown store so users don't lose memory.

    Durable *active* preference claims from the old ``memory.json`` become
    standing preferences. The old episodic events are intentionally NOT migrated
    (they carried the deprecated "chose X because Y" framing). Legacy files are
    renamed ``*.bak`` so this runs once. Guarded against re-entry because
    ``add_preference`` itself reads preferences.
    """
    global _MIGRATING
    if _MIGRATING:
        return
    memory_json, events_jsonl = _legacy_paths()
    if not memory_json.exists() and not events_jsonl.exists():
        return
    _MIGRATING = True
    try:
        import json

        imported = 0
        if memory_json.exists():
            try:
                data = json.loads(memory_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            for claim in data.get("claims", []):
                if not isinstance(claim, dict) or claim.get("status") != "active":
                    continue
                statement = _clean(claim.get("statement", ""))
                area = claim.get("area", "other")
                if not statement:
                    continue
                try:
                    add_preference(area if area in _AREAS else "other", statement)
                    imported += 1
                except GoalsError:
                    continue
        for path in (memory_json, events_jsonl):
            if path.exists():
                path.replace(path.with_name(path.name + ".bak"))
        if imported:
            _note_migration(imported)
    finally:
        _MIGRATING = False


def _note_migration(count: int) -> None:
    path = preferences_path()
    note = (
        f"<!-- Imported {count} preference(s) from your previous Goals memory; "
        "the old files were kept alongside as *.bak. -->"
    )
    with lock_file(path):
        lines = _read_lines(path, _PREFERENCES_HEADER)
        if note not in lines:
            header_end = 1
            while header_end < len(lines) and lines[header_end].lstrip().startswith("<!--"):
                header_end += 1
            lines.insert(header_end, note)
            atomic_write_text(path, "\n".join(lines).rstrip() + "\n")


# Interview bookkeeping lives in the observations log as HTML-comment markers —
# invisible in rendered Markdown, ignored by the observation parser, and kept out
# of any JSON so everything under ~/.goals/user/ stays hand-editable Markdown.
def _marker(kind: str, slug: str) -> str:
    return f"<!-- goals:{kind} goal:{slug} -->"


def _has_marker(slug: str, kinds: tuple[str, ...]) -> bool:
    if not slug:
        return False
    path = observations_path()
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return any(_marker(kind, slug) in text for kind in kinds)


def _append_marker(kind: str, slug: str) -> None:
    if not slug:
        return
    path = observations_path()
    with lock_file(path):
        lines = _read_lines(path, _OBSERVATIONS_HEADER)
        marker = _marker(kind, slug)
        if marker not in lines:
            lines.append(marker)
            atomic_write_text(path, "\n".join(lines).rstrip() + "\n")


def _extract_statements(text: str) -> list[str]:
    statements: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw).strip()
        if len(line) < 8:
            continue
        statement = _clean(line)
        key = statement.lower()
        if key in seen:
            continue
        seen.add(key)
        statements.append(statement)
        if len(statements) >= 8:
            break
    if not statements and text.strip():
        statements.append(_clean(text.strip()[:320]))
    return [statement for statement in statements if statement]


# Signal words for inferring a preference's area from free text (interview
# answers, where the user didn't pick an area). Best-effort; ties and misses
# fall back to ``decision``.
_AREA_KEYWORDS: dict[str, tuple[str, ...]] = {
    "risk": ("risk", "reversible", "irreversible", "safe", "cautious", "destructive", "danger"),
    "communication": (
        "explain", "concise", "verbose", "detail", "plain", "jargon", "summary", "tone", "brief",
    ),
    "workflow": ("test", "commit", "branch", "step", "process", "review", "plan", "order", "first"),
    "technical": (
        "language", "framework", "library", "stack", "architecture", "database", "api", "tool",
    ),
    "decision": ("decide", "ask", "choose", "autonomy", "confirm", "approval", "permission"),
}


def infer_area(text: str, fallback: str = "decision") -> str:
    low = text.lower()
    scores = {
        area: sum(1 for word in words if word in low)
        for area, words in _AREA_KEYWORDS.items()
    }
    best = max(scores, key=lambda area: scores[area])
    return best if scores[best] else fallback


def _validate_area(value: str) -> UserPreferenceArea:
    candidate = (value or "").strip().lower()
    if candidate not in _AREAS:
        raise GoalsError(f"Unknown area '{value}'. Choose one of: {', '.join(_AREAS)}.")
    return candidate  # type: ignore[return-value]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _slug(value: str) -> str:
    return _clean(value).replace(" ", "-")
