"""The verdict rubric: a read-time view that maps mechanical gate facts to a human
category vocabulary.

The gate kernel (``goals.gates``) emits ``GateFactType`` facts and never names a
category. This module is the *only* place the facts are interpreted into the
audience-facing ``GateFindingCategory`` rubric, so the vocabulary can change — or a
different audience can frame the same proof facts differently — without touching the
kernel or rewriting persisted proof history.
"""

from __future__ import annotations

from collections.abc import Sequence

from goals.models import GateFactType, GateFinding, GateFindingCategory

# One swappable map. A fact with no entry falls back to VERIFICATION_MISS — the safe
# "proof is weak/absent" reading — so a new fact never crashes the presentation layer.
_FACT_CATEGORY: dict[GateFactType, GateFindingCategory] = {
    GateFactType.ACCEPTANCE_NOT_MET: GateFindingCategory.GAP,
    GateFactType.CHECK_FAILED: GateFindingCategory.BUG,
    GateFactType.NO_EVIDENCE: GateFindingCategory.VERIFICATION_MISS,
    GateFactType.AMBIGUOUS: GateFindingCategory.VERIFICATION_MISS,
    GateFactType.VERIFICATION_UNRUNNABLE: GateFindingCategory.VERIFICATION_MISS,
    GateFactType.NO_PASSING_CHECK: GateFindingCategory.VERIFICATION_MISS,
    GateFactType.MISSING_FALSIFIER: GateFindingCategory.VERIFICATION_MISS,
}

# Most concrete/actionable first: a BUG (a check demonstrably failed) outranks a GAP
# (work admittedly unfinished), which outranks a VERIFICATION_MISS (proof not wired).
_CATEGORY_RANK: dict[GateFindingCategory, int] = {
    GateFindingCategory.BUG: 3,
    GateFindingCategory.GAP: 2,
    GateFindingCategory.VERIFICATION_MISS: 1,
}


def category_for(fact_type: GateFactType) -> GateFindingCategory:
    """Map one mechanical fact to its human category."""
    return _FACT_CATEGORY.get(fact_type, GateFindingCategory.VERIFICATION_MISS)


def representative_category(
    findings: Sequence[GateFinding],
) -> GateFindingCategory | None:
    """Collapse many findings into the single most important category, or None."""
    categories = [category_for(finding.fact_type) for finding in findings]
    if not categories:
        return None
    return max(categories, key=lambda category: _CATEGORY_RANK[category])
