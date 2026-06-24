"""Goal-execution memory: small, private, and human-editable.

Two plain-Markdown files under ``~/.goals/user/`` — both yours to read and edit:

- ``preferences.md`` — durable preferences that steer how Goals auto-executes.
  You own it. Goals only adds to it when you state or confirm a preference;
  it never rewrites your edits.
- ``observations.md`` — an append-only log of situated decisions Goals saw you
  make while a goal ran: *what* you chose and the *context*, never an invented
  reason. A quoted note is only ever your own words.

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
    JudgementObservation,
    PersonalizationContext,
    Preference,
    UserMemory,
    UserPreferenceArea,
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
    "<!-- Goals appends one decision per line as you work — the choice and its "
    "context, never an invented reason. -->\n"
    "<!-- A note in quotes is only ever your own words. Edit a line only to "
    "correct it. -->\n"
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


def forget_preference(target: str, *, purge: bool = False) -> int:
    """Remove preference bullets matching ``target`` (substring, case-insensitive).

    ``target == '--all'`` clears every preference; with ``purge`` it deletes the
    files outright. Returns the number of preferences removed.
    """
    if target == "--all":
        before = len(load_preferences())
        if purge:
            for path in (preferences_path(), observations_path()):
                path.unlink(missing_ok=True)
            return before
        path = preferences_path()
        with lock_file(path):
            atomic_write_text(path, _PREFERENCES_HEADER)
        return before
    needle = _clean(target).lower()
    if not needle:
        raise GoalsError("Provide preference text to forget, or use --all.")
    path = preferences_path()
    with lock_file(path):
        if not path.exists():
            return 0
        kept: list[str] = []
        removed = 0
        for raw in path.read_text(encoding="utf-8").splitlines():
            bullet = re.match(r"^[-*]\s+(.*)$", raw.strip())
            if bullet and needle in bullet.group(1).lower():
                removed += 1
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
) -> JudgementObservation:
    clean_note = _clean(note)
    observation = JudgementObservation(
        goal_id=_slug(goal_id),
        area=_validate_area(area),
        choice=_clean(choice),
        context=_clean(context),
        note=clean_note,
        # A reason is "stated" only when the user gave one; we never infer it.
        provenance="stated" if clean_note else "observed",
    )
    if not observation.choice:
        raise GoalsError("An observation needs a choice.")
    path = observations_path()
    with lock_file(path):
        lines = _read_lines(path, _OBSERVATIONS_HEADER)
        lines.append(_format_observation_line(observation))
        atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
    return observation


def load_observations() -> list[JudgementObservation]:
    path = observations_path()
    if not path.exists():
        return []
    observations: list[JudgementObservation] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        observation = _parse_observation_line(raw)
        if observation is not None:
            observations.append(observation)
    return observations


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
    )


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
    areas: tuple[str, str, str] = ("decision", "workflow", "communication")
    preferences = [add_preference(area, text) for area, text in zip(areas, clean)]
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


def _format_observation_line(observation: JudgementObservation) -> str:
    date = observation.created_at[:10]
    parts = [
        f"- {date}",
        f"goal:{observation.goal_id or 'none'}",
        f"[{observation.area}] chose: {observation.choice}",
    ]
    line = f" {_MIDDOT} ".join(parts)
    if observation.context:
        line += f" — when: {observation.context}"
    if observation.note:
        line += f' (you said: "{observation.note}")'
    return line


_OBS_RE = re.compile(
    r"^-\s+(?P<date>\d{4}-\d{2}-\d{2})\s+·\s+goal:(?P<goal>\S*)\s+·\s+"
    r"\[(?P<area>[^\]]+)\]\s+chose:\s+(?P<rest>.*)$"
)


def _parse_observation_line(raw: str) -> JudgementObservation | None:
    match = _OBS_RE.match(raw.strip())
    if not match:
        return None
    rest = match.group("rest")
    note = ""
    note_match = re.search(r'\s*\(you said:\s*"(?P<note>.*)"\)\s*$', rest)
    if note_match:
        note = note_match.group("note")
        rest = rest[: note_match.start()]
    context = ""
    if " — when: " in rest:
        choice, context = rest.split(" — when: ", 1)
    else:
        choice = rest
    area = match.group("area").strip().lower()
    goal = match.group("goal")
    return JudgementObservation(
        goal_id="" if goal == "none" else goal,
        area=area if area in _AREAS else "other",  # type: ignore[arg-type]
        choice=_clean(choice),
        context=_clean(context),
        note=_clean(note),
        provenance="stated" if note else "observed",
        created_at=match.group("date"),
    )


def _describe_observation(observation: JudgementObservation) -> str:
    text = f"chose {observation.choice}"
    if observation.context:
        text += f" — when {observation.context}"
    if observation.note:
        text += f' (you said: "{observation.note}")'
    if observation.goal_id:
        text += f" [goal:{observation.goal_id}]"
    return text


def _recurring_candidates(
    observations: list[JudgementObservation],
    preferences: list[Preference],
) -> list[tuple[str, str, int]]:
    """Choices made in >= 2 distinct goals that aren't already a preference."""
    seen: dict[tuple[str, str], set[str]] = {}
    for obs in observations:
        if not obs.choice or not obs.goal_id:
            continue
        seen.setdefault((obs.area, obs.choice), set()).add(obs.goal_id)
    covered = {(pref.area, pref.text.lower()) for pref in preferences}
    candidates = [
        (choice, area, len(goals))
        for (area, choice), goals in seen.items()
        if len(goals) >= 2 and (area, choice.lower()) not in covered
    ]
    candidates.sort(key=lambda item: item[2], reverse=True)
    return candidates


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


def _validate_area(value: str) -> UserPreferenceArea:
    candidate = (value or "").strip().lower()
    if candidate not in _AREAS:
        raise GoalsError(f"Unknown area '{value}'. Choose one of: {', '.join(_AREAS)}.")
    return candidate  # type: ignore[return-value]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _slug(value: str) -> str:
    return _clean(value).replace(" ", "-")
