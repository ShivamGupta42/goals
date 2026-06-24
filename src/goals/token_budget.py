"""Deterministic token accounting for the enforced Stop gate.

Goals does not run the model loop, so it cannot meter spend directly. But the
Claude Code Stop hook hands the plugin the session ``transcript_path``, and the
transcript records per-call token ``usage``. Summing that is a deterministic
proxy for spend — no USD, no model call, no estimate — which lets the Stop gate
enforce a token ceiling the same way it enforces a review-attempt cap.

Tokens are summed *per call*: each assistant turn re-bills the whole input
context, so the running total tracks tokens billed rather than the size of the
final transcript. That is the right quantity for a runaway-cost guard.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

#: The usage fields a Claude transcript reports per assistant turn. All four are
#: billed, so the ceiling counts their sum.
_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


def transcript_token_usage(path: Path | str) -> TokenUsage:
    """Sum token usage across every turn in a Claude Code transcript (JSONL).

    Deterministic and defensive: a missing file, blank lines, malformed JSON, or
    a turn without usage all contribute nothing rather than raising — the caller
    is a fail-open hook, and an unreadable transcript must never trip (or block)
    the gate on a phantom count.
    """
    totals = dict.fromkeys(_USAGE_KEYS, 0)
    file = Path(path)
    if not file.exists():
        return TokenUsage()
    with file.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            usage = _usage_of(event)
            if usage is None:
                continue
            for key in _USAGE_KEYS:
                value = usage.get(key)
                # bool is an int subclass; exclude it so a stray ``true`` can't
                # inflate the count. Require a positive int so a negative field
                # can't subtract from the running total and hold the ceiling off.
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    totals[key] += value
    return TokenUsage(**totals)


def _usage_of(event: object) -> dict | None:
    """Find the ``usage`` dict on a transcript event, if it has one.

    Handles both the nested shape (``{"message": {"usage": {...}}}``) and a
    top-level ``usage`` key, ignoring anything that isn't a dict.
    """
    if not isinstance(event, dict):
        return None
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("usage"), dict):
        return message["usage"]
    usage = event.get("usage")
    return usage if isinstance(usage, dict) else None
