from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from goals.models import Event, EventType, SourceClaim, SourceRecord, SourceFreshnessReport
from goals.runtime import append_event, load_active_snapshot
from goals.sources import analyze_source_freshness


@dataclass(frozen=True)
class SourceListReport:
    sources: list[SourceRecord]
    claims: list[SourceClaim]


def record_source(
    cwd: Path,
    source: SourceRecord,
    *,
    claims: list[SourceClaim] | None = None,
) -> SourceRecord:
    snapshot = load_active_snapshot(cwd)
    append_event(
        cwd,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.SOURCE_RECORDED,
            payload={
                "source": source.model_dump(),
                "claims": [item.model_dump() for item in (claims or [])],
            },
        ),
    )
    return source


def source_list(cwd: Path) -> SourceListReport:
    snapshot = load_active_snapshot(cwd)
    return SourceListReport(sources=list(snapshot.sources), claims=list(snapshot.source_claims))


def source_freshness(
    cwd: Path,
    *,
    max_age_days: int | None = None,
) -> SourceFreshnessReport:
    return analyze_source_freshness(load_active_snapshot(cwd), max_age_days=max_age_days)
