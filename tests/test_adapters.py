from __future__ import annotations

from dataclasses import dataclass

import goals.adapters as adapters
from goals.adapters import adapter_check


@dataclass
class FakeCompleted:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def stub_run(monkeypatch, *, result=None, raises=None) -> list:
    """Patch subprocess.run and return a list that records each call's command."""
    calls: list = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if raises is not None:
            raise raises
        return result

    monkeypatch.setattr(adapters.subprocess, "run", fake_run)
    return calls


def test_codex_single_word_state(monkeypatch) -> None:
    calls = stub_run(
        monkeypatch,
        result=FakeCompleted(0, stdout="goals                experimental       false\n"),
    )
    ready, detail = adapter_check("codex")
    assert ready is False
    assert detail == "goals feature: experimental (enabled=false)"
    # No padded whitespace leaks from the raw table row.
    assert "  " not in detail
    assert calls == [["codex", "features", "list"]]


def test_codex_multi_word_state_enabled(monkeypatch) -> None:
    stub_run(
        monkeypatch,
        result=FakeCompleted(0, stdout="goals    under development    true\n"),
    )
    ready, detail = adapter_check("codex")
    assert ready is True
    assert detail == "goals feature: under development (enabled=true)"
    assert "  " not in detail


def test_codex_goals_line_missing(monkeypatch) -> None:
    stub_run(
        monkeypatch,
        result=FakeCompleted(0, stdout="apps    stable    true\n"),
    )
    ready, detail = adapter_check("codex")
    assert ready is False
    assert detail == "Codex goals feature not found."


def test_codex_executable_not_found(monkeypatch) -> None:
    stub_run(monkeypatch, raises=FileNotFoundError())
    ready, detail = adapter_check("codex")
    assert ready is False
    assert detail == "Codex executable not found."


def test_codex_nonzero_returncode_returns_stderr(monkeypatch) -> None:
    stub_run(monkeypatch, result=FakeCompleted(1, stderr="boom"))
    ready, detail = adapter_check("codex")
    assert ready is False
    assert detail == "boom"


def test_claude_version_happy_path(monkeypatch) -> None:
    calls = stub_run(monkeypatch, result=FakeCompleted(0, stdout="claude 1.2.3\n"))
    ready, detail = adapter_check("claude")
    assert ready is True
    assert detail == "claude 1.2.3"
    assert calls == [["claude", "--version"]]


def test_claude_executable_not_found(monkeypatch) -> None:
    stub_run(monkeypatch, raises=FileNotFoundError())
    ready, detail = adapter_check("claude")
    assert ready is False
    assert detail == "Claude executable not found."


def test_unknown_adapter(monkeypatch) -> None:
    ready, detail = adapter_check("mystery")
    assert ready is False
    assert detail == "Unknown adapter: mystery"
