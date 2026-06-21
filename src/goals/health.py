from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from goals.architecture import analyze_code_architecture
from goals.brief import build_goal_brief
from goals.capabilities import analyze_capabilities
from goals.checkpoints import build_current_checkpoint_brief
from goals.issues import AnalyzerResults, analyze_goal_issues
from goals.merge_readiness import analyze_merge_readiness
from goals.models import (
    ArchitectureCheckReport,
    CapabilityCheckReport,
    CurrentCheckpointBrief,
    GoalBrief,
    GoalIssueReport,
    GoalSnapshot,
    MergeReadinessReport,
    SourceFreshnessReport,
)
from goals.registry import validate_registries
from goals.sources import analyze_source_freshness


@dataclass(frozen=True)
class GoalHealthReport:
    snapshot: GoalSnapshot
    brief: GoalBrief
    checkpoint: CurrentCheckpointBrief
    issues: GoalIssueReport
    merge: MergeReadinessReport
    architecture: ArchitectureCheckReport
    capability: CapabilityCheckReport
    source_freshness: SourceFreshnessReport
    registry_count: int

    @property
    def passed(self) -> bool:
        return (
            not self.issues.issues
            and self.merge.passed
            and self.architecture.passed
            and self.capability.passed
        )

    @property
    def analyzer_results(self) -> AnalyzerResults:
        return AnalyzerResults(
            capability=self.capability,
            architecture=self.architecture,
            merge=self.merge,
            source_freshness=self.source_freshness,
        )


def build_goal_health(
    snapshot: GoalSnapshot,
    worktree: Path,
    *,
    inventory: Any | None = None,
) -> GoalHealthReport:
    """Assemble goal health once, without rendering or writing artifacts."""
    capability = analyze_capabilities(snapshot, inventory=inventory)
    architecture = analyze_code_architecture(snapshot, worktree)
    merge = analyze_merge_readiness(snapshot)
    source_freshness = analyze_source_freshness(snapshot)
    analyzer_results = AnalyzerResults(
        capability=capability,
        architecture=architecture,
        merge=merge,
        source_freshness=source_freshness,
    )
    issues = analyze_goal_issues(snapshot, analyzer_results=analyzer_results)
    return GoalHealthReport(
        snapshot=snapshot,
        brief=build_goal_brief(snapshot),
        checkpoint=build_current_checkpoint_brief(snapshot),
        issues=issues,
        merge=merge,
        architecture=architecture,
        capability=capability,
        source_freshness=source_freshness,
        registry_count=len(validate_registries(worktree)),
    )
