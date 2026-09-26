"""Guard the Discovery (phase one) commands against flag drift.

The same commands are quoted in three files, and two CLI defaults are unsafe for
phase one: ``checkpoint record --status`` defaults to ``passed`` (the alignment
gate silently never blocks) and ``decision record --by`` defaults to ``user`` (the
agent's recommendation is logged as the user's decision). A ``--depends``
assumption on P1 stalls Confirm, because nothing is built to falsify yet.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DISCOVERY_DOCS = [
    REPO / "commands" / "create.md",
    REPO / "commands" / "discover.md",
    REPO / "skills" / "goals-discovery" / "SKILL.md",
]
COMMAND_RE = re.compile(
    r"goals (?:checkpoint record|decision record|assess assume|assess want)[^`\n]*"
)


def _commands(path: Path, prefix: str) -> list[str]:
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    return [" ".join(m.group(0).split()) for m in COMMAND_RE.finditer(text) if m.group(0).startswith(prefix)]


def test_alignment_checkpoint_states_status_and_gates_on_the_user() -> None:
    for path in DISCOVERY_DOCS:
        commands = _commands(path, "goals checkpoint record P1 alignment")
        assert commands, f"{path.name} should quote the alignment checkpoint command"
        for command in commands:
            assert "--status " in command, f"{path.name}: alignment command omits --status: {command}"
        assert any("--status needs_user" in command for command in commands), (
            f"{path.name}: alignment checkpoint must be recorded with --status needs_user"
        )


def test_discovery_decisions_state_who_decided_and_where() -> None:
    # --phase P1 is how DISCOVERY.md finds the approach decisions.
    for path in DISCOVERY_DOCS:
        for command in _commands(path, "goals decision record"):
            assert "--by " in command, f"{path.name}: decision record omits --by: {command}"
            assert "--phase P1" in command, f"{path.name}: decision record omits --phase P1: {command}"


def test_discovery_never_puts_a_load_bearing_assumption_on_confirm() -> None:
    for path in DISCOVERY_DOCS:
        for command in _commands(path, "goals assess assume"):
            if "--depends" not in command.split():
                continue
            phase = re.search(r"--phase (\S+)", command)
            assert phase and phase.group(1) != "P1", (
                f"{path.name}: --depends assumption must name a later --phase: {command}"
            )


def test_discovery_never_binds_a_desired_property_to_confirm() -> None:
    for path in DISCOVERY_DOCS:
        for command in _commands(path, "goals assess want"):
            assert "--phase P1" not in command, f"{path.name}: property bound to P1: {command}"
            if "--proof auto" in command:
                assert "--phase " in command, f"{path.name}: auto proof needs --phase: {command}"


def test_discovery_uses_typed_properties_not_stand_ins() -> None:
    # Never dual-write: the stand-ins (assumptions + hand-made P4 feel-* checkpoints)
    # were replaced by `goals assess want` in the same release.
    for path in DISCOVERY_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "feel-" not in text, f"{path.name} still documents feel-* checkpoints"
        assert not any("--depends" in c for c in _commands(path, "goals assess assume")), path.name


def test_command_extraction_sees_multiline_and_inline_forms() -> None:
    skill = DISCOVERY_DOCS[2]
    assert any("--proof auto --phase P3" in c for c in _commands(skill, "goals assess want"))
    assert any("--by agent" in c for c in _commands(skill, "goals decision record"))
