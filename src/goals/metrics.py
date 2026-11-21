"""A read-only report of how past goals went, built from their own event logs.

``goals metrics`` answers one question: across the goals of this repo, how did
the phases go? It counts what Goals already records (review verdicts and which
kind of check backed each phase) and nothing else. It never writes, never calls
a model, and is not shown to the agent: it is for the person who wants to judge
whether a change to Goals helped.

Logs are read as plain lines rather than through the strict event loader, so an
older log with fewer fields, or one odd line, is counted and skipped instead of
stopping the report.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from goals.git_ops import find_git_root, list_worktrees
from goals.proof_summary import PROOF_LABELS

_REASON_LIMIT = 100
_NON_PASS_SHOWN = 10


class NonPassReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    verdict: str
    reason: str = ""


class GoalMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    log_path: str
    first_event: str = ""
    last_event: str = ""
    phases_reviewed: int = 0
    first_review_passed: int = 0
    first_review_by_phase: dict[str, str] = Field(default_factory=dict)
    review_attempts: int = 0
    review_verdicts: dict[str, int] = Field(default_factory=dict)
    non_pass_reviews: list[NonPassReview] = Field(default_factory=list)
    #: Kind of each check in the latest evidence of every phase (auto, manual, ...). An auto
    #: check the engine never ran shows as ``not_run``.
    proof_kinds: dict[str, int] = Field(default_factory=dict)
    #: False when no phase has checks recorded (an older log, or a goal not yet at evidence).
    proof_recorded: bool = False
    user_replies: int = 0
    skipped_lines: int = 0


class MetricsTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goals: int = 0
    phases_reviewed: int = 0
    first_review_passed: int = 0
    first_review_by_phase: dict[str, dict[str, int]] = Field(default_factory=dict)
    review_attempts: int = 0
    review_verdicts: dict[str, int] = Field(default_factory=dict)
    proof_kinds: dict[str, int] = Field(default_factory=dict)
    goals_without_proof_kinds: int = 0
    user_replies: int = 0
    skipped_lines: int = 0


class MetricsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goals: list[GoalMetrics] = Field(default_factory=list)
    unreadable: list[str] = Field(default_factory=list)
    totals: MetricsTotals = Field(default_factory=MetricsTotals)


# --------------------------------------------------------------------------- #
# Finding and reading logs
# --------------------------------------------------------------------------- #
def find_goal_logs(cwd: Path) -> list[Path]:
    """Return every ``events.jsonl`` for this repo's goals, including linked worktrees."""
    repo = find_git_root(cwd) or cwd.resolve()
    roots = [record["path"] for record in list_worktrees(repo) if isinstance(record["path"], Path)]
    roots = roots or [repo]
    seen: dict[Path, None] = {}
    for root in roots:
        goals_dir = root / ".agent-workflow" / "goals"
        if not goals_dir.is_dir():
            continue
        for log in sorted(goals_dir.glob("*/events.jsonl")):
            seen[log.resolve()] = None
    return list(seen)


def summarize_log(path: Path) -> GoalMetrics:
    """Summarize one goal's log. Raises OSError or UnicodeDecodeError if the file can't be read."""
    verdicts_by_phase: dict[str, list[str]] = {}
    non_pass: list[NonPassReview] = []
    declared: dict[str, dict[str, str]] = {}  # phase -> {check id: kind} from latest evidence
    ran: dict[str, set[str]] = {}  # phase -> ids the engine ran since that evidence
    replies = skipped = 0
    first_ts = last_ts = ""
    # Split on "\n" only: str.splitlines() also splits on U+2028/U+2029/U+0085, which the
    # engine writes unescaped inside a JSON string, and would cut one event in two.
    for line in path.read_text(encoding="utf-8").split("\n"):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            skipped += 1
            continue
        if not isinstance(event, dict) or not isinstance(event.get("event_type"), str):
            skipped += 1
            continue
        stamp = event.get("timestamp")
        if isinstance(stamp, str) and stamp:
            first_ts = first_ts or stamp
            last_ts = stamp
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        kind = event["event_type"]
        if kind == "user_message_recorded":
            replies += 1
        elif kind == "phase_reviewed":
            review = _review_of(payload)
            if review is None:
                skipped += 1  # a review with no phase or verdict says nothing we can count
            else:
                phase, verdict, reason = review
                verdicts_by_phase.setdefault(phase, []).append(verdict)
                if verdict != "pass":
                    non_pass.append(NonPassReview(phase=phase, verdict=verdict, reason=reason))
        elif kind == "phase_evidence":
            phase = payload.get("phase_id")
            if isinstance(phase, str):
                declared[phase] = _declared_checks(payload.get("evidence"))
                ran[phase] = set()  # new evidence has to be verified again
        elif kind == "phase_verified":
            phase = payload.get("phase_id")
            if isinstance(phase, str):
                ran[phase] = _ran_ids(payload.get("verifications"))
    verdicts = Counter(v for vs in verdicts_by_phase.values() for v in vs)
    proof = Counter(
        "not_run" if check_kind == "auto" and check_id not in ran.get(phase, set()) else check_kind
        for phase, checks in declared.items()
        for check_id, check_kind in checks.items()
    )
    return GoalMetrics(
        goal=path.parent.name,
        log_path=str(path),
        first_event=first_ts,
        last_event=last_ts,
        phases_reviewed=len(verdicts_by_phase),
        first_review_passed=sum(vs[0] == "pass" for vs in verdicts_by_phase.values()),
        first_review_by_phase={p: vs[0] for p, vs in _by_phase(verdicts_by_phase)},
        review_attempts=sum(verdicts.values()),
        review_verdicts=dict(verdicts),
        non_pass_reviews=non_pass,
        proof_kinds=dict(proof),
        proof_recorded=bool(proof),
        user_replies=replies,
        skipped_lines=skipped,
    )


def build_metrics_report(cwd: Path) -> MetricsReport:
    """Read every goal log of this repo. A log that cannot be read is listed, not fatal."""
    goals: list[GoalMetrics] = []
    unreadable: list[str] = []
    for log in find_goal_logs(cwd):
        try:
            goals.append(summarize_log(log))
        except (OSError, UnicodeDecodeError):
            unreadable.append(str(log))
    goals.sort(key=lambda g: (g.first_event, g.goal))
    return MetricsReport(goals=goals, unreadable=unreadable, totals=_totals(goals))


def _review_of(payload: dict) -> tuple[str, str, str] | None:
    phase = payload.get("phase_id")
    gate = payload.get("gate_result")
    verdict = gate.get("verdict") if isinstance(gate, dict) else None
    if not isinstance(phase, str) or not isinstance(verdict, str):
        return None
    p0 = gate.get("p0")
    reason = p0[0] if isinstance(p0, list) and p0 and isinstance(p0[0], str) else ""
    reason = reason or (gate.get("summary") if isinstance(gate.get("summary"), str) else "")
    return phase, verdict, _cut(reason)


def _declared_checks(evidence: object) -> dict[str, str]:
    checks = evidence.get("verifications") if isinstance(evidence, dict) else None
    if not isinstance(checks, list):
        return {}
    declared: dict[str, str] = {}
    for index, check in enumerate(checks):
        if isinstance(check, dict):
            check_id = check.get("verification_id")
            kind = check.get("kind")
            declared[check_id if isinstance(check_id, str) else f"#{index}"] = (
                kind if isinstance(kind, str) else "unknown"
            )
    return declared


def _ran_ids(checks: object) -> set[str]:
    if not isinstance(checks, list):
        return set()
    return {
        c["verification_id"]
        for c in checks
        if isinstance(c, dict)
        and c.get("ran") is True
        and isinstance(c.get("verification_id"), str)
    }


def _by_phase(items: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
    return sorted(items.items(), key=lambda kv: (len(kv[0]), kv[0]))


def _cut(text: str, limit: int = _REASON_LIMIT) -> str:
    # A lone surrogate in a damaged log would make printing or JSON output raise.
    text = " ".join(text.split()).encode("utf-8", "replace").decode("utf-8")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _totals(goals: list[GoalMetrics]) -> MetricsTotals:
    by_phase: dict[str, dict[str, int]] = {}
    verdicts: Counter[str] = Counter()
    proof: Counter[str] = Counter()
    for g in goals:
        verdicts.update(g.review_verdicts)
        proof.update(g.proof_kinds)
        for phase, first in g.first_review_by_phase.items():
            row = by_phase.setdefault(phase, {"reviewed": 0, "passed": 0})
            row["reviewed"] += 1
            row["passed"] += first == "pass"
    ordered = dict(sorted(by_phase.items(), key=lambda kv: (len(kv[0]), kv[0])))
    return MetricsTotals(
        goals=len(goals),
        phases_reviewed=sum(g.phases_reviewed for g in goals),
        first_review_passed=sum(g.first_review_passed for g in goals),
        first_review_by_phase=ordered,
        review_attempts=sum(g.review_attempts for g in goals),
        review_verdicts=dict(verdicts),
        proof_kinds=dict(proof),
        goals_without_proof_kinds=sum(not g.proof_recorded for g in goals),
        user_replies=sum(g.user_replies for g in goals),
        skipped_lines=sum(g.skipped_lines for g in goals),
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_metrics_report(report: MetricsReport) -> str:
    t = report.totals
    if not report.goals and not report.unreadable:
        return "No goals found for this repo, so there is nothing to count. Nothing was changed."
    lines = [
        f"Goals metrics: {t.goals} goal(s) read from their event logs. Nothing was changed.",
        "",
    ]
    lines.append("Did each phase pass its first review?")
    for phase, row in t.first_review_by_phase.items():
        lines.append(f"  {phase}: {row['passed']} of {row['reviewed']} passed first time")
    lines.append(f"  All phases: {t.first_review_passed} of {t.phases_reviewed} passed first time")
    lines += ["", f"All review attempts: {t.review_attempts} ({_counts(t.review_verdicts)})"]
    lines.append(f"Checks behind the phases: {_proof_text(t)}")
    lines += ["", "Each goal (oldest first)"]
    for g in report.goals:
        lines.append(f"  - {g.goal}: {_span(g)}; {_goal_line(g)}")
    if any(g.non_pass_reviews for g in report.goals):
        rows = [(g.goal, r) for g in report.goals for r in g.non_pass_reviews]
        lines += ["", f"Reviews that did not pass ({len(rows)})"]
        for goal, r in rows[:_NON_PASS_SHOWN]:
            why = f": {r.reason}" if r.reason else ""
            lines.append(f"  - {goal} {r.phase} {r.verdict}{why}")
        if len(rows) > _NON_PASS_SHOWN:
            lines.append(f"  (+{len(rows) - _NON_PASS_SHOWN} more; see --json)")
    if t.skipped_lines:
        lines += [
            "",
            f"Skipped {t.skipped_lines} damaged or incomplete line(s) in the logs.",
        ]
    for path in report.unreadable:
        lines.append(f"Could not read: {path}")
    lines += [
        "",
        "This counts what Goals recorded. It does not tell you why a review failed "
        "or whether the work was good.",
    ]
    return "\n".join(lines)


def _counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{n} {name}" for name, n in sorted(counts.items(), key=lambda kv: -kv[1]))


def _proof_text(t: MetricsTotals) -> str:
    if not t.proof_kinds:
        return "not recorded in any log"
    parts = ", ".join(
        f"{n} {PROOF_LABELS.get(kind, kind)}"
        for kind, n in sorted(t.proof_kinds.items(), key=lambda kv: -kv[1])
    )
    if t.goals_without_proof_kinds:
        parts += f" ({t.goals_without_proof_kinds} goal(s) have no checks recorded)"
    return parts


def _span(g: GoalMetrics) -> str:
    if not g.first_event:
        return "no dates recorded"
    start, end = g.first_event[:10], g.last_event[:10]
    return start if start == end else f"{start} to {end}"


def _goal_line(g: GoalMetrics) -> str:
    checks = (
        ", ".join(f"{n} {PROOF_LABELS.get(k, k)}" for k, n in sorted(g.proof_kinds.items()))
        if g.proof_kinds
        else "not recorded"
    )
    return (
        f"{g.first_review_passed} of {g.phases_reviewed} phases passed first time, "
        f"{g.review_attempts} review attempt(s); checks: {checks}"
    )
