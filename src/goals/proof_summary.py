"""One plain line saying how a goal's proof was made.

``Checks: 18 run by the engine, 1 by hand (P4.C3), 0 waived``

It counts the checks recorded on *one* goal's own phases, from its saved state. It
shows how much of the proof the engine ran itself and how much was written by hand,
so weak proof is visible where people already look: `goals check`, `goals brief`, the
dashboard and `goals finish`. It is display only; no gate reads it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from goals.models import GoalSnapshot

# The words used for each kind of check. The cross-goal report shares this table, so
# the two reports describe a check the same way.
PROOF_LABELS = {
    "auto": "run by the engine",
    "manual": "by hand",
    "waived": "waived",
    "production": "checked in production",
    "not_run": "declared but not run",
}

_IDS_SHOWN = 3
_ID_LIMIT = 24


class ProofSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: int = 0
    engine_failed: int = 0
    not_run: int = 0
    by_hand: list[str] = Field(default_factory=list)
    waived: list[str] = Field(default_factory=list)
    production: list[str] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.engine + self.not_run + len(self.by_hand) + len(self.waived) + len(self.production)
        )


def summarize_proof(snapshot: GoalSnapshot) -> ProofSummary:
    """Count the checks on every phase's latest evidence, by how they were made."""
    summary = ProofSummary()
    for phase in snapshot.phases:
        if phase.evidence is None:
            continue
        for check in phase.evidence.verifications:
            if check.kind == "auto":
                # Only the engine sets `ran`; an auto check it never ran is just declared.
                if not check.ran:
                    summary.not_run += 1
                    continue
                summary.engine += 1
                if not check.passed:
                    summary.engine_failed += 1
            elif check.kind == "manual":
                summary.by_hand.append(check.covers)
            elif check.kind == "waived":
                summary.waived.append(check.covers)
            elif check.kind == "production":
                summary.production.append(check.covers)
    return summary


def render_proof_line(snapshot: GoalSnapshot) -> str:
    """The one-line summary; says so plainly when no checks are recorded yet."""
    summary = summarize_proof(snapshot)
    if summary.total == 0:
        return "Checks: none recorded yet"
    engine = f"{summary.engine} {PROOF_LABELS['auto']}"
    if summary.engine_failed:
        engine += f" ({summary.engine_failed} failed)"
    parts = [
        engine,
        _kind_text(summary.by_hand, PROOF_LABELS["manual"], always=True),
        _kind_text(summary.waived, PROOF_LABELS["waived"], always=True),
        _kind_text(summary.production, PROOF_LABELS["production"]),
    ]
    if summary.not_run:
        parts.append(f"{summary.not_run} {PROOF_LABELS['not_run']}")
    return "Checks: " + ", ".join(part for part in parts if part)


def _kind_text(ids: list[str], label: str, *, always: bool = False) -> str:
    """'N label (id, id +M more)'. Zero is shown only for kinds worth seeing as zero."""
    if not ids:
        return f"0 {label}" if always else ""
    shown = ", ".join(_cut(i) for i in ids[:_IDS_SHOWN])
    more = f" +{len(ids) - _IDS_SHOWN} more" if len(ids) > _IDS_SHOWN else ""
    return f"{len(ids)} {label} ({shown}{more})"


def _cut(text: str) -> str:
    """An id for the brackets: no brackets or commas of its own, never empty, cut short.

    `covers` is written by the agent, so it must not be able to imitate the line's own
    structure (a stray ')' or ', 0 waived') or leave empty brackets.
    """
    for mark in "(),":
        text = text.replace(mark, " ")
    text = " ".join(text.split()) or "unnamed"
    return text if len(text) <= _ID_LIMIT else text[: _ID_LIMIT - 1] + "…"
