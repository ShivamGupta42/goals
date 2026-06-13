from __future__ import annotations

from pathlib import Path

from goals.git_ops import git_root
from goals.models import (
    GateVerdict,
    GoalSnapshot,
    MemorySyncCandidate,
    MemorySyncPlan,
    SelfEvolutionEntry,
    SelfEvolutionMemory,
    SelfEvolutionSuggestion,
    utc_now,
)
from goals.storage import GoalsError, atomic_write_text


def memory_path(cwd: Path, snapshot: GoalSnapshot | None = None) -> Path:
    root = _memory_root(cwd, snapshot)
    return root / ".agent-workflow" / "self-evolution" / "memory.json"


def load_memory(cwd: Path, snapshot: GoalSnapshot | None = None) -> SelfEvolutionMemory:
    path = memory_path(cwd, snapshot)
    if not path.exists():
        return SelfEvolutionMemory()
    try:
        return SelfEvolutionMemory.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GoalsError(f"Invalid self-evolution memory at {path}: {exc}") from exc


def save_memory(
    cwd: Path,
    memory: SelfEvolutionMemory,
    snapshot: GoalSnapshot | None = None,
) -> Path:
    path = memory_path(cwd, snapshot)
    memory.updated_at = utc_now()
    atomic_write_text(path, memory.model_dump_json(indent=2) + "\n")
    return path


def append_memory_entry(
    cwd: Path,
    entry: SelfEvolutionEntry,
    snapshot: GoalSnapshot | None = None,
) -> SelfEvolutionMemory:
    memory = load_memory(cwd, snapshot)
    if not any(existing.entry_id == entry.entry_id for existing in memory.entries):
        memory.entries.append(entry)
    save_memory(cwd, memory, snapshot)
    return memory


def plan_memory_sync(
    cwd: Path,
    source: Path,
    snapshot: GoalSnapshot | None = None,
    *,
    include_private: bool = False,
    limit: int = 20,
) -> MemorySyncPlan:
    source_path = resolve_memory_source(source)
    source_memory = _load_memory_file(source_path)
    target_path = memory_path(cwd, snapshot)
    if source_path == target_path.resolve():
        raise GoalsError("Cross-project memory source is the current project memory.")
    target_memory = load_memory(cwd, snapshot)
    source_label = _source_label(source_path) if include_private else "external-project"
    existing_notes = {(entry.area, entry.note) for entry in target_memory.entries}
    candidates: list[MemorySyncCandidate] = []
    skipped: list[MemorySyncCandidate] = []
    for suggestion in derive_memory_suggestions(source_memory)[:limit]:
        candidate = _sync_candidate(suggestion, source_label, include_private)
        note = _sync_note(candidate, include_private)
        if (candidate.area, note) in existing_notes:
            skipped.append(candidate.model_copy(update={"skip_reason": "Already imported."}))
            continue
        candidates.append(candidate)
    if candidates:
        summary = (
            f"Prepared {len(candidates)} cross-project memory import(s) from {source_label}. "
            "Dry run only; use --apply after reviewing."
        )
        agent_actions = [
            "Review the importable suggestions.",
            "Apply only if the lessons are relevant to this project.",
        ]
    else:
        summary = f"No new actionable cross-project memory suggestions found in {source_label}."
        agent_actions = [
            "Keep recording local friction with `goals memory record` until patterns repeat."
        ]
    return MemorySyncPlan(
        source_path=str(source_path),
        source_label=source_label,
        target_path=str(target_path),
        dry_run=True,
        include_private=include_private,
        candidates=candidates,
        skipped=skipped,
        summary=summary,
        agent_actions=agent_actions,
        user_questions=[],
    )


def apply_memory_sync(
    cwd: Path,
    plan: MemorySyncPlan,
    snapshot: GoalSnapshot | None = None,
) -> MemorySyncPlan:
    memory = load_memory(cwd, snapshot)
    existing_notes = {(entry.area, entry.note) for entry in memory.entries}
    imported = 0
    for candidate in plan.candidates:
        note = _sync_note(candidate, plan.include_private)
        if (candidate.area, note) in existing_notes:
            continue
        memory.entries.append(
            SelfEvolutionEntry(
                kind="learning",
                area=candidate.area,  # type: ignore[arg-type]
                note=note,
                severity=candidate.severity,
                goal_id=snapshot.goal_id if snapshot is not None else "",
                phase_id=snapshot.current_phase if snapshot is not None else None,
                evidence_refs=candidate.evidence_refs,
            )
        )
        existing_notes.add((candidate.area, note))
        imported += 1
    if imported:
        save_memory(cwd, memory, snapshot)
    summary = (
        f"Imported {imported} cross-project memory suggestion(s) from {plan.source_label}."
        if imported
        else f"No new cross-project memory suggestions imported from {plan.source_label}."
    )
    return plan.model_copy(
        update={
            "dry_run": False,
            "imported_count": imported,
            "summary": summary,
            "agent_actions": [
                "Run `goals memory suggest` to see how imported lessons affect this project.",
                "Keep imported lessons local unless the user chooses to publish a sanitized change.",
            ],
        }
    )


def resolve_memory_source(source: Path) -> Path:
    source = source.expanduser()
    if source.is_dir():
        source = source / ".agent-workflow" / "self-evolution" / "memory.json"
    if not source.exists():
        raise GoalsError(f"Cross-project memory source not found: {source}")
    if not source.is_file():
        raise GoalsError(f"Cross-project memory source is not a file: {source}")
    return source.resolve()


def render_memory_sync_plan(plan: MemorySyncPlan) -> str:
    lines = [
        "# Cross-Project Memory Sync",
        "",
        f"Mode: {'dry run' if plan.dry_run else 'applied'}",
        f"Source: {plan.source_label}",
        f"Importable suggestions: {len(plan.candidates)}",
        f"Skipped suggestions: {len(plan.skipped)}",
        f"Imported suggestions: {plan.imported_count}",
        "",
        plan.summary,
    ]
    if plan.candidates:
        lines.extend(["", "## Importable Suggestions", ""])
        for candidate in plan.candidates:
            lines.extend(
                [
                    f"- {candidate.title} ({candidate.severity}, {candidate.occurrences} occurrence(s))",
                    f"  Recommended change: {candidate.recommended_change}",
                ]
            )
            if candidate.suggested_command:
                lines.append(f"  Suggested command: `{candidate.suggested_command}`")
    if plan.skipped:
        lines.extend(["", "## Skipped Suggestions", ""])
        for candidate in plan.skipped:
            lines.append(f"- {candidate.title}: {candidate.skip_reason}")
    lines.extend(["", "## Agent Actions", "", _bullets(plan.agent_actions)])
    if plan.dry_run and plan.candidates:
        lines.extend(["", "Run again with `--apply` to import the sanitized suggestions."])
    return "\n".join(lines) + "\n"


def absorb_goal_memory(cwd: Path, snapshot: GoalSnapshot) -> list[SelfEvolutionEntry]:
    entries: list[SelfEvolutionEntry] = []
    for phase in snapshot.phases:
        if phase.evidence is not None:
            for gap in phase.evidence.known_gaps:
                entries.append(_entry(snapshot, "gap", "phase", gap, "medium", phase.phase_id))
            for ambiguous in phase.evidence.ambiguous:
                entries.append(
                    _entry(snapshot, "friction", "decision", ambiguous, "medium", phase.phase_id)
                )
            if phase.evidence.acceptance_not_met:
                entries.append(
                    _entry(
                        snapshot,
                        "friction",
                        "gate",
                        "; ".join(phase.evidence.acceptance_not_met),
                        "high",
                        phase.phase_id,
                    )
                )
        for review in phase.reviews:
            if review.verdict != GateVerdict.PASS:
                area = "safety" if review.verdict == GateVerdict.UNSAFE else "gate"
                note_parts = [review.summary, *review.p0, *review.p1]
                entries.append(
                    _entry(
                        snapshot,
                        "friction",
                        area,
                        "; ".join(part for part in note_parts if part),
                        "high" if review.p0 or review.verdict == GateVerdict.UNSAFE else "medium",
                        phase.phase_id,
                    )
                )
    for blocker in snapshot.blockers:
        entries.append(
            _entry(snapshot, "friction", "phase", blocker, "high", snapshot.current_phase)
        )
    for learning in snapshot.learnings:
        entries.append(
            _entry(snapshot, "learning", "other", learning, "low", snapshot.current_phase)
        )
    memory = load_memory(cwd, snapshot)
    existing_keys = {_entry_key(entry) for entry in memory.entries}
    new_entries = [entry for entry in entries if _entry_key(entry) not in existing_keys]
    if new_entries:
        memory.entries.extend(new_entries)
        save_memory(cwd, memory, snapshot)
    return new_entries


def derive_memory_suggestions(memory: SelfEvolutionMemory) -> list[SelfEvolutionSuggestion]:
    groups: dict[tuple[str, str], list[SelfEvolutionEntry]] = {}
    for entry in memory.entries:
        if entry.kind == "success":
            continue
        groups.setdefault((entry.area, entry.kind), []).append(entry)
    suggestions = []
    for (area, kind), entries in groups.items():
        if not _is_actionable(entries):
            continue
        severity = _group_severity(entries)
        suggestions.append(
            SelfEvolutionSuggestion(
                area=area,
                title=_suggestion_title(area, kind),
                plain_summary=_summary(entries),
                recommended_change=_recommended_change(area, kind),
                occurrences=len(entries),
                severity=severity,
                evidence_refs=_evidence_refs(entries),
                user_visible=severity == "high"
                or len(entries) >= 2
                or _has_cross_project_memory(entries),
                suggested_command=_suggested_command(area),
            )
        )
    suggestions.sort(
        key=lambda item: (_severity_rank(item.severity), item.occurrences), reverse=True
    )
    return suggestions


def render_memory_suggestions(suggestions: list[SelfEvolutionSuggestion]) -> str:
    if not suggestions:
        return "- No repeated self-evolution friction recorded."
    return "\n".join(
        (
            f"- {suggestion.title}: {suggestion.plain_summary} "
            f"Recommended change: {suggestion.recommended_change}"
            + (
                f" Suggested command: `{suggestion.suggested_command}`."
                if suggestion.suggested_command
                else ""
            )
        )
        for suggestion in suggestions
    )


def _memory_root(cwd: Path, snapshot: GoalSnapshot | None) -> Path:
    if snapshot is not None and snapshot.topology.base_repo:
        return Path(snapshot.topology.base_repo)
    return git_root(cwd)


def _entry(
    snapshot: GoalSnapshot,
    kind: str,
    area: str,
    note: str,
    severity: str,
    phase_id: str | None,
) -> SelfEvolutionEntry:
    return SelfEvolutionEntry(
        kind=kind,  # type: ignore[arg-type]
        area=area,  # type: ignore[arg-type]
        note=note,
        severity=severity,  # type: ignore[arg-type]
        goal_id=snapshot.goal_id,
        phase_id=phase_id,
    )


def _entry_key(entry: SelfEvolutionEntry) -> tuple[str, str, str, str | None]:
    return (entry.goal_id, entry.area, entry.note, entry.phase_id)


def _is_actionable(entries: list[SelfEvolutionEntry]) -> bool:
    return (
        len(entries) >= 2
        or any(entry.severity == "high" for entry in entries)
        or _has_cross_project_memory(entries)
    )


def _group_severity(entries: list[SelfEvolutionEntry]) -> str:
    if any(entry.severity == "high" for entry in entries):
        return "high"
    if len(entries) >= 3 or any(entry.severity == "medium" for entry in entries):
        return "medium"
    return "low"


def _severity_rank(severity: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}[severity]


def _summary(entries: list[SelfEvolutionEntry]) -> str:
    first = entries[-1].note
    if len(entries) == 1:
        return first
    return f"{len(entries)} related observations. Latest: {first}"


def _evidence_refs(entries: list[SelfEvolutionEntry]) -> list[str]:
    refs: list[str] = []
    for entry in entries:
        refs.extend(entry.evidence_refs)
        if entry.goal_id:
            refs.append(entry.goal_id)
    return sorted(set(refs))


def _suggestion_title(area: str, kind: str) -> str:
    labels = {
        "adapter": "Improve adapter guidance",
        "architecture": "Improve architecture map guidance",
        "dashboard": "Improve dashboard visibility",
        "decision": "Improve decision handling",
        "docs": "Improve documentation",
        "ecosystem": "Improve skill/plugin routing",
        "gate": "Improve review gates",
        "phase": "Improve phase breakdown",
        "safety": "Improve safety checks",
        "skill": "Improve or add a skill",
        "test": "Improve validation checks",
        "other": "Capture a reusable learning",
    }
    return labels.get(area, f"Improve {area}") + f" after {kind}"


def _recommended_change(area: str, kind: str) -> str:
    changes = {
        "adapter": "Update Mode A instructions so agents avoid this repeated issue earlier.",
        "architecture": "Update the architecture map schema or prompt guidance.",
        "dashboard": "Make the dashboard expose this status in plain language.",
        "decision": "Tighten the decision rule or explainer so ambiguity is resolved sooner.",
        "docs": "Update README, roadmap, or examples to make the expected workflow clearer.",
        "ecosystem": "Add registry hints or tool recommendations for this recurring pattern.",
        "gate": "Strengthen the gate criteria or add a specialized gate.",
        "phase": "Adjust default phases or acceptance criteria.",
        "safety": "Add a scanner fixture or safety rule.",
        "skill": "Update an existing skill or add a new skill route for this pattern.",
        "test": "Add or improve validation coverage.",
        "other": "Turn the observation into a small product or documentation improvement.",
    }
    change = changes.get(area, "Record a targeted improvement.")
    if kind == "gap":
        return f"{change} Treat it as a missing capability."
    return change


def _suggested_command(area: str) -> str:
    commands = {
        "dashboard": "goals dashboard",
        "decision": "goals decision explain --file decision.json --level basic",
        "ecosystem": "goals ecosystem recommend",
        "safety": "goals safety-check --mode local .",
        "test": "uv run pytest -q",
    }
    return commands.get(area, "")


def _load_memory_file(path: Path) -> SelfEvolutionMemory:
    try:
        return SelfEvolutionMemory.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GoalsError(f"Invalid cross-project memory at {path}: {exc}") from exc


def _source_label(path: Path) -> str:
    parts = path.parts
    if ".agent-workflow" in parts:
        index = parts.index(".agent-workflow")
        if index > 0:
            return parts[index - 1]
    return path.stem


def _sync_candidate(
    suggestion: SelfEvolutionSuggestion,
    source_label: str,
    include_private: bool,
) -> MemorySyncCandidate:
    evidence_refs = [f"cross-project-memory:{source_label}:{suggestion.area}"]
    if include_private:
        evidence_refs.extend(suggestion.evidence_refs)
    return MemorySyncCandidate(
        source_label=source_label,
        area=suggestion.area,
        title=suggestion.title,
        plain_summary=suggestion.plain_summary if include_private else "",
        recommended_change=suggestion.recommended_change,
        occurrences=suggestion.occurrences,
        severity=suggestion.severity,
        suggested_command=suggestion.suggested_command,
        evidence_refs=sorted(set(evidence_refs)),
    )


def _sync_note(candidate: MemorySyncCandidate, include_private: bool) -> str:
    note = (
        f"Cross-project learning from {candidate.source_label}: {candidate.title}. "
        f"Recommended change: {candidate.recommended_change}"
    )
    if include_private and candidate.plain_summary:
        note += f" Source pattern: {candidate.plain_summary}"
    return note


def _has_cross_project_memory(entries: list[SelfEvolutionEntry]) -> bool:
    return any(
        ref.startswith("cross-project-memory:") for entry in entries for ref in entry.evidence_refs
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None."
