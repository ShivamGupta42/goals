from __future__ import annotations

from dataclasses import dataclass

from goals.models import Phase


@dataclass(frozen=True)
class CriterionRef:
    criterion_id: str
    text: str


def criterion_id(phase_id: str, index: int) -> str:
    """Stable enough criterion id for the current string-based phase schema."""

    return f"{phase_id}.C{index + 1}"


def criterion_refs(phase: Phase) -> list[CriterionRef]:
    return [
        CriterionRef(criterion_id(phase.phase_id, index), text)
        for index, text in enumerate(phase.acceptance_criteria)
    ]


def criterion_cover_aliases(phase: Phase, ref: CriterionRef) -> set[str]:
    """Accepted coverage tokens for a criterion.

    New evidence should cover the id (e.g. P1.C1). Legacy evidence often covered
    verbatim text, so text remains an alias during the schema transition.
    """

    return {ref.criterion_id, ref.text}
