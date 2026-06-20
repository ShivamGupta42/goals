from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from goals.models import Event, EventType, GoalSnapshot
from goals.storage import EventStore, GoalsError


class ArtifactMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_id: str
    path: str
    reason: str
    expected_sha256: str = ""
    actual_sha256: str = ""


class GoalAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    passed: bool
    strict: bool = False
    event_count: int = 0
    snapshot_matches: bool = False
    registry_count: int = 0
    dangling_causes: list[str] = Field(default_factory=list)
    artifact_mismatches: list[ArtifactMismatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EventLineageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    actor: str
    caused_by: str | None = None
    phase_id: str = ""
    timestamp: str = ""
    summary: str = ""


class EventLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    chains: list[list[EventLineageItem]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def build_audit_report(
    goal_dir: Path,
    *,
    worktree: Path,
    strict: bool = False,
    registry_count: int = 0,
) -> GoalAuditReport:
    store = EventStore(goal_dir)
    events = store.read_events()
    if not events:
        raise GoalsError("No events found for this goal.")
    derived = store.snapshot()
    snapshot_matches = False
    warnings: list[str] = []
    if store.snapshot_path.exists():
        try:
            stored = GoalSnapshot.model_validate_json(store.snapshot_path.read_text(encoding="utf-8"))
            snapshot_matches = stored.model_dump(mode="json") == derived.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Stored snapshot could not be read: {exc}")
    else:
        warnings.append("Derived snapshot file is missing.")

    dangling = _dangling_causes(events)
    raw_warnings = _legacy_event_warnings(store.events_path)
    artifact_mismatches = _artifact_mismatches(derived, worktree)
    warnings.extend(raw_warnings)
    warnings.extend(_artifact_warnings(derived))
    passed = snapshot_matches and (not strict or (not dangling and not artifact_mismatches))
    return GoalAuditReport(
        goal_id=derived.goal_id,
        passed=passed,
        strict=strict,
        event_count=len(events),
        snapshot_matches=snapshot_matches,
        registry_count=registry_count,
        dangling_causes=dangling,
        artifact_mismatches=artifact_mismatches,
        warnings=warnings,
    )


def build_event_lineage(events: list[Event], event_id: str) -> EventLineage:
    by_id = {event.event_id: event for event in events}
    if event_id not in by_id:
        raise GoalsError(f"Unknown event id: {event_id}")
    chain, warnings = _chain_to_root(by_id, event_id)
    return EventLineage(target=event_id, chains=[chain], warnings=warnings)


def build_phase_lineage(events: list[Event], phase_id: str) -> EventLineage:
    by_id = {event.event_id: event for event in events}
    phase_events = [event for event in events if event.payload.get("phase_id") == phase_id]
    if not phase_events:
        raise GoalsError(f"No events found for phase: {phase_id}")
    chains: list[list[EventLineageItem]] = []
    warnings: list[str] = []
    for event in phase_events[-5:]:
        chain, chain_warnings = _chain_to_root(by_id, event.event_id)
        chains.append(chain)
        warnings.extend(chain_warnings)
    return EventLineage(target=phase_id, chains=chains, warnings=list(dict.fromkeys(warnings)))


def render_audit_report(report: GoalAuditReport) -> str:
    lines = [
        f"Validated goal {report.goal_id}; registries={report.registry_count}"
        if report.passed
        else f"Validation failed for {report.goal_id}.",
        f"Events: {report.event_count}",
        f"Snapshot matches log: {'yes' if report.snapshot_matches else 'no'}",
        f"Registries: {report.registry_count}",
    ]
    if not report.snapshot_matches:
        lines.append("Derived snapshot does not match the event log. Run `goals repair`.")
    if report.strict:
        lines.append(f"Dangling causes: {len(report.dangling_causes)}")
        lines.append(f"Artifact mismatches: {len(report.artifact_mismatches)}")
    if report.dangling_causes:
        lines.append("\nDangling causes:")
        lines.extend(f"- {item}" for item in report.dangling_causes)
    if report.artifact_mismatches:
        lines.append("\nArtifact mismatches:")
        for mismatch in report.artifact_mismatches:
            lines.append(f"- {mismatch.phase_id}: {mismatch.path} ({mismatch.reason})")
    if report.warnings:
        lines.append("\nWarnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines)


def render_lineage(lineage: EventLineage) -> str:
    lines = [f"Lineage for {lineage.target}:"]
    for index, chain in enumerate(lineage.chains, start=1):
        if len(lineage.chains) > 1:
            lines.append(f"\nChain {index}:")
        for item in chain:
            phase = f" phase={item.phase_id}" if item.phase_id else ""
            lines.append(
                f"- {item.event_id} {item.event_type}{phase} actor={item.actor}: {item.summary}"
            )
    if lineage.warnings:
        lines.append("\nWarnings:")
        lines.extend(f"- {warning}" for warning in lineage.warnings)
    return "\n".join(lines)


def summarize_event(event: Event) -> EventLineageItem:
    phase_id = event.payload.get("phase_id")
    return EventLineageItem(
        event_id=event.event_id,
        event_type=str(event.event_type),
        actor=event.actor,
        caused_by=event.caused_by,
        phase_id=phase_id if isinstance(phase_id, str) else "",
        timestamp=event.timestamp,
        summary=_event_summary(event),
    )


def _chain_to_root(
    by_id: dict[str, Event], event_id: str
) -> tuple[list[EventLineageItem], list[str]]:
    chain: list[EventLineageItem] = []
    warnings: list[str] = []
    seen: set[str] = set()
    current_id: str | None = event_id
    while current_id:
        if current_id in seen:
            warnings.append(f"Causal cycle detected at {current_id}.")
            break
        seen.add(current_id)
        event = by_id.get(current_id)
        if event is None:
            warnings.append(f"Missing causal event {current_id}.")
            break
        chain.append(summarize_event(event))
        current_id = event.caused_by
    chain.reverse()
    return chain, warnings


def _event_summary(event: Event) -> str:
    payload = event.payload
    if event.event_type == EventType.GOAL_CREATED:
        snapshot = payload.get("snapshot", {})
        if isinstance(snapshot, dict):
            return str(snapshot.get("objective", "goal created"))
    if event.event_type == EventType.PHASE_EVIDENCE:
        evidence = payload.get("evidence", {})
        if isinstance(evidence, dict):
            return f"evidence recorded ({len(evidence.get('verifications', []))} verification(s))"
    if event.event_type == EventType.PHASE_VERIFIED:
        return f"verified {len(payload.get('verifications', []))} check(s)"
    if event.event_type == EventType.PHASE_REVIEWED:
        gate = payload.get("gate_result", {})
        if isinstance(gate, dict):
            return str(gate.get("summary", "phase reviewed"))
    if event.event_type == EventType.PHASE_ACCEPTED:
        return "phase accepted"
    if event.event_type == EventType.DECISION_RECORDED:
        judgement = payload.get("judgement", {})
        if isinstance(judgement, dict):
            return str(judgement.get("question", "decision recorded"))
    if event.event_type == EventType.ASSUMPTION_RECORDED:
        assumption = payload.get("assumption", {})
        if isinstance(assumption, dict):
            return str(assumption.get("statement", "assumption recorded"))
    return str(event.event_type).replace("_", " ")


def _dangling_causes(events: list[Event]) -> list[str]:
    ids = {event.event_id for event in events}
    return [
        f"{event.event_id} caused_by={event.caused_by}"
        for event in events
        if event.caused_by and event.caused_by not in ids
    ]


def _legacy_event_warnings(events_path: Path) -> list[str]:
    if not events_path.exists():
        return []
    warnings: list[str] = []
    known = {member.value for member in EventType}
    for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = data.get("event_type")
        if isinstance(event_type, str) and event_type not in known:
            continue
        missing = [key for key in ("actor", "trace_id") if key not in data]
        if missing:
            event_id = data.get("event_id", f"line {line_number}")
            warnings.append(f"{event_id} is a legacy event missing {', '.join(missing)}.")
    return warnings


def _artifact_warnings(snapshot: GoalSnapshot) -> list[str]:
    warnings: list[str] = []
    for phase in snapshot.phases:
        if phase.evidence and phase.evidence.changed_files and not phase.evidence.artifacts:
            warnings.append(
                f"{phase.phase_id} lists changed files but has no artifact hashes; run phase verify."
            )
    return warnings


def _artifact_mismatches(snapshot: GoalSnapshot, worktree: Path) -> list[ArtifactMismatch]:
    mismatches: list[ArtifactMismatch] = []
    for phase in snapshot.phases:
        evidence = phase.evidence
        if evidence is None:
            continue
        for artifact in evidence.artifacts:
            if artifact.error:
                mismatches.append(
                    ArtifactMismatch(
                        phase_id=phase.phase_id,
                        path=artifact.path,
                        reason=artifact.error,
                        expected_sha256=artifact.sha256,
                    )
                )
                continue
            path = _artifact_path(worktree, artifact.path)
            if path is None:
                mismatches.append(
                    ArtifactMismatch(
                        phase_id=phase.phase_id,
                        path=artifact.path,
                        reason="path escapes worktree",
                        expected_sha256=artifact.sha256,
                    )
                )
                continue
            if artifact.missing or not path.exists():
                mismatches.append(
                    ArtifactMismatch(
                        phase_id=phase.phase_id,
                        path=artifact.path,
                        reason="missing",
                        expected_sha256=artifact.sha256,
                    )
                )
                continue
            if not path.is_file():
                mismatches.append(
                    ArtifactMismatch(
                        phase_id=phase.phase_id,
                        path=artifact.path,
                        reason="not a file",
                        expected_sha256=artifact.sha256,
                    )
                )
                continue
            actual = _sha256(path)
            if actual != artifact.sha256:
                mismatches.append(
                    ArtifactMismatch(
                        phase_id=phase.phase_id,
                        path=artifact.path,
                        reason="sha256 mismatch",
                        expected_sha256=artifact.sha256,
                        actual_sha256=actual,
                    )
                )
    return mismatches


def _artifact_path(worktree: Path, raw: str) -> Path | None:
    path = Path(raw)
    if path.is_absolute():
        return None
    resolved = (worktree / path).resolve()
    try:
        resolved.relative_to(worktree.resolve())
    except ValueError:
        return None
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
