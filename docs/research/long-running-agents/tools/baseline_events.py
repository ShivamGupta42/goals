"""Count what Goals' own event logs already say about how goals ran.

Read-only. Takes one or more ``events.jsonl`` paths and prints one JSON object per goal:
review verdicts, phases that passed their first review, the proof mix (auto, manual,
waived) taken from the latest evidence of each phase, checkpoint events and recorded
user replies. Used by ``improvement-plan.md`` to show a baseline costs nothing to build.

Usage: python3 -I baseline_events.py PATH/events.jsonl [PATH/events.jsonl ...]
"""

import json
import sys
from collections import Counter
from pathlib import Path


def summarize(path: Path) -> dict:
    """Summarize one goal's event log."""
    verdicts_by_phase: dict[str, list[str]] = {}
    latest_evidence: dict[str, list[dict]] = {}
    counts: Counter[str] = Counter()
    first_ts = last_ts = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        kind = event["event_type"]
        payload = event["payload"]
        counts[kind] += 1
        first_ts = first_ts or event["timestamp"]
        last_ts = event["timestamp"]
        if kind == "phase_reviewed":
            phase = payload["phase_id"]
            verdicts_by_phase.setdefault(phase, []).append(payload["gate_result"]["verdict"])
        elif kind == "phase_evidence":
            evidence = payload.get("evidence") or {}
            latest_evidence[payload["phase_id"]] = evidence.get("verifications") or []
    verdicts = Counter(v for vs in verdicts_by_phase.values() for v in vs)
    proof = Counter(v.get("kind", "?") for vs in latest_evidence.values() for v in vs)
    return {
        "goal": path.parent.name,
        "first_event": first_ts,
        "last_event": last_ts,
        "phases_reviewed": len(verdicts_by_phase),
        "first_review_passed": sum(vs[0] == "pass" for vs in verdicts_by_phase.values()),
        "review_attempts": sum(verdicts.values()),
        "review_verdicts": dict(verdicts),
        "proof_kinds": dict(proof),
        "checkpoint_events": counts["phase_checkpoint_recorded"],
        "user_replies": counts["user_message_recorded"],
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        print(json.dumps(summarize(Path(arg))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
