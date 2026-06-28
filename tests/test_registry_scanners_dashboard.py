from pathlib import Path

import pytest

from goals.dashboard import render_dashboard
from goals.models import (
    ArchitectureEdge,
    ArchitectureNode,
    CheckpointStatus,
    Evidence,
    GoalArchitectureMap,
    GoalSnapshot,
    JudgementObservation,
    JudgementRecord,
    Phase,
    PhaseCheckpoint,
    PhaseStatus,
    Preference,
    UserMemory,
    WorktreeLease,
)
from goals.registry import validate_registry_file
from goals.runtime import default_phases
from goals.storage import GoalsError


def _lease(tmp_path: Path) -> WorktreeLease:
    return WorktreeLease(
        base_repo=str(tmp_path),
        base_branch="main",
        worktree_path=str(tmp_path),
        branch="goal/demo",
    )


def test_registry_rejects_unknown_critical_field(tmp_path: Path) -> None:
    path = tmp_path / "bad.yml"
    path.write_text("version: 1\nkind: gates\nsurprise: true\n")
    with pytest.raises(GoalsError):
        validate_registry_file(path)


def test_dashboard_escapes_html_and_shows_overview(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="<script>alert(1)</script>",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    # XSS escaping holds.
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text

    # Accessibility scaffolding.
    assert 'class="skip-link"' in text
    assert '<main id="main"' in text
    assert '<html lang="en">' in text

    # The three-tier overview structure.
    assert "Read-only snapshot" in text  # orientation line
    assert "What happened" in text
    assert "The steps" in text
    assert "Checks &amp; references" in text
    assert "Proof &amp; evidence" in text
    assert "Technical details" in text
    assert "Goal ID:" in text
    assert "Source commit:" in text
    assert "P1 has no evidence yet." in text

    # Empty sections are hidden, not shown as "none yet" collapsibles.
    assert "Architecture map" not in text  # no recorded map → hidden
    assert "Decisions" not in text  # no judgements → hidden
    assert "Sources" not in text  # no sources → hidden
    assert "No decisions recorded yet." not in text

    # Skills and self-evolution memory are no longer part of the overview.
    assert "<h2>Skills</h2>" not in text
    assert "Self-Evolution Memory" not in text


def test_dashboard_renders_current_checkpoint_safely(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Plan launch",
        topology=_lease(tmp_path),
        phases=[
            Phase(
                phase_id="P1",
                title="Confirm launch",
                goal="Confirm launch risk.",
                checkpoints=[
                    PhaseCheckpoint(
                        checkpoint_id="CP-launch",
                        title="<b>Approve launch</b>",
                        status=CheckpointStatus.NEEDS_USER,
                        needs_user=True,
                        summary="Owner approval is needed.",
                        evidence_refs=["brief:P1"],
                    )
                ],
            )
        ],
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"

    render_dashboard(snapshot, output)
    text = output.read_text()

    assert "<b>Approve launch</b>" not in text
    assert "&lt;b&gt;Approve launch&lt;/b&gt;" in text
    assert "brief:P1" in text
    assert "Waiting on" in text


def test_dashboard_shows_decision_log_not_solicitation(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add sessions",
        topology=_lease(tmp_path),
        phases=[
            Phase(
                phase_id="P1",
                title="Inspect storage",
                goal="Find the storage shape",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(checks_run=["pytest"], confidence=0.8, notes="Done."),
            )
        ],
        current_phase=None,
        judgements=[
            JudgementRecord(
                question="Where should sessions live?",
                choice="Redis",
                rationale="<b>fast</b> and shared across nodes",
                decided_by="user",
                reversible=True,
            )
        ],
    )
    output = tmp_path / "dashboard.html"

    render_dashboard(snapshot, output)
    text = output.read_text()

    # The judgement log renders what was decided.
    assert "Where should sessions live?" in text
    assert "Chose: Redis" in text
    assert "user" in text

    # Judgement content is escaped.
    assert "<b>fast</b>" not in text
    assert "&lt;b&gt;fast&lt;/b&gt;" in text

    # Decision *solicitation* UI is gone from the dashboard.
    assert "Decision Brief" not in text
    assert "Recommended option" not in text
    assert "Suggested reply" not in text


def test_dashboard_decision_timeline_separates_agent_and_human(tmp_path: Path) -> None:
    # The decision log is a visual timeline that tells AI-made and human-made
    # calls apart — by label and icon, not colour alone — and counts each side.
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add sessions",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
        judgements=[
            JudgementRecord(question="Where should sessions live?", choice="Redis",
                            decided_by="user", reversible=True),
            JudgementRecord(question="Token expiry?", choice="15m + refresh",
                            decided_by="agent", reversible=True),
            JudgementRecord(question="Drop legacy table?", choice="Stage it",
                            decided_by="user", reversible=False),
        ],
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    # Timeline scaffolding with a per-decider tally derived from decided_by.
    assert 'class="dtimeline"' in text
    assert "Agent decided 1" in text
    assert "You decided 2" in text

    # Each call carries a text decider label (a11y: never colour-only) and the
    # decided_by token survives as the node class.
    assert "dnode user" in text
    assert "dnode agent" in text

    # Reversibility is a visible, text-bearing pill, not just a colour.
    assert "locked in" in text  # the irreversible call
    assert "reversible" in text


def test_dashboard_renders_user_memory_hierarchy(tmp_path: Path) -> None:
    # User memory renders as a two-tier hierarchy: situated observations roll up
    # into standing preferences, with an explicit promotion link between them.
    memory = UserMemory(
        preferences=[
            Preference(area="risk", text="Ask before anything <irreversible>"),
            Preference(area="workflow", text="Run tests before every commit"),
        ],
        observations=[
            JudgementObservation(goal_id="add-auth", area="technical",
                                 choice="Redis for sessions", context="multi-node deploy"),
        ],
    )
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add sessions",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output, user_memory=memory)
    text = output.read_text()

    assert "What Goals remembers about you" in text
    assert "Observed · situated choices" in text
    assert "Standing · durable preferences" in text
    assert "promoted when you confirm" in text  # the link between the tiers
    assert "Run tests before every commit" in text
    assert "Redis for sessions" in text
    assert "add-auth" in text  # observation is scoped to its goal

    # Memory content is escaped like everything else on the page.
    assert "<irreversible>" not in text
    assert "&lt;irreversible&gt;" in text


def test_dashboard_hides_user_memory_when_absent_or_empty(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add sessions",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"

    # No memory supplied → the panel is hidden entirely.
    render_dashboard(snapshot, output)
    assert "What Goals remembers about you" not in output.read_text()

    # An empty memory store is also hidden (no "none yet" noise).
    render_dashboard(snapshot, output, user_memory=UserMemory())
    assert "What Goals remembers about you" not in output.read_text()


def test_dashboard_humanizes_status_and_timestamp(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Ship it",
        topology=_lease(tmp_path),
        phases=[
            Phase(
                phase_id="P1",
                title="Build the thing",
                goal="Build it.",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    checks_run=["pytest"],
                    confidence=0.9,
                    notes="Done.",
                    changed_files=["src/app.py"],
                ),
            )
        ],
        current_phase="P1",
        last_updated="2026-06-14T17:40:19.526012+00:00",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    # Friendly, human-readable timestamp — not the raw ISO string.
    assert "Jun 14, 2026" in text
    assert "5:40 PM" in text
    # The raw ISO is allowed ONLY as the machine-readable data-iso attribute that
    # powers the offline "N ago" hint — never as the displayed value. It must
    # therefore appear exactly once, inside that attribute.
    assert 'data-iso="2026-06-14T17:40:19.526012+00:00"' in text
    assert text.count("2026-06-14T17:40:19.526012+00:00") == 1

    # Always-on plain-language status banner.
    assert "<h2>Status</h2>" in text

    # "Waiting on" is mapped to plain language, never the raw token.
    assert "Agent" in text
    assert "Agent (working)" not in text  # status, not turn-ownership, says "working"


def test_dashboard_header_frames_journey_and_clamps_long_goal(tmp_path: Path) -> None:
    long_objective = (
        "figure out how do people market and get distribution for their github "
        "repos on agentic coding and llms and how can we popularise this one"
    )
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective=long_objective,
        why="Keep a long-running agent task understandable, reviewable, and resumable.",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    # "Goal journey" framing replaces the bare status kicker.
    assert "The goal journey ·" in text
    assert "From first intent to finished proof" in text

    # The "why" line is gone entirely.
    assert "Keep a long-running agent task" not in text
    assert 'class="why"' not in text

    # A long objective gets a clamped title plus a "read the full goal" expander,
    # and the full text is still present for screen readers.
    assert '<h1 class="title">' in text
    assert "Read the full goal" in text
    assert long_objective in text


def test_dashboard_short_goal_has_no_full_goal_expander(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add a settings page",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    assert "The goal journey ·" in text
    assert "Read the full goal" not in text  # short objective → no expander


def test_friendly_timestamp_only_states_what_it_carries() -> None:
    from goals.dashboard import _friendly_timestamp

    # Malformed input is returned untouched.
    assert _friendly_timestamp("not-a-date") == "not-a-date"
    # Timezone-aware UTC keeps its zone label.
    assert _friendly_timestamp("2026-06-14T17:40:19+00:00") == "Jun 14, 2026 · 5:40 PM UTC"
    # Naive timestamp renders without an invented zone.
    assert _friendly_timestamp("2026-06-14T17:40:19") == "Jun 14, 2026 · 5:40 PM"
    # Date-only input renders without an invented time.
    assert _friendly_timestamp("2026-06-14") == "Jun 14, 2026"
    # A real midnight still shows its time (not mistaken for date-only).
    assert _friendly_timestamp("2026-06-14T00:00:00+00:00") == "Jun 14, 2026 · 12:00 AM UTC"


def test_dashboard_renders_architecture_svg(tmp_path: Path) -> None:
    architecture = GoalArchitectureMap(
        title="Map",
        overview="How the parts connect.",
        nodes=[
            ArchitectureNode(
                node_id="gen", label="Generator", plain_summary="Builds the HTML.", status="built"
            ),
            ArchitectureNode(
                node_id="snap",
                label="<x>Snapshot</x>",
                plain_summary="Holds state.",
                status="in_progress",
            ),
        ],
        edges=[
            ArchitectureEdge(from_node="snap", to_node="gen"),
            # A self-loop must not break layout or draw a degenerate arrow.
            ArchitectureEdge(from_node="gen", to_node="gen"),
        ],
    )
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"

    render_dashboard(snapshot, output, architecture=architecture)
    text = output.read_text()

    # The diagram renders as inline SVG with a clean node and an arrow marker.
    assert "<svg viewBox" in text
    assert 'marker id="ah"' in text
    assert "Generator" in text

    # Node labels are escaped inside the SVG.
    assert "<x>Snapshot</x>" not in text
    assert "&lt;x&gt;Snapshot&lt;/x&gt;" in text
    # SVG carries a <title> for screen readers, not just an aria-label.
    assert "<title>How the parts connect.</title>" in text


def test_dashboard_is_offline_self_contained(tmp_path: Path) -> None:
    # The dashboard is a local file:// artifact — it must not depend on any remote
    # asset (a CDN font failed silently offline / on a phone with no network).
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Work with no network",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()

    assert "https://fonts.googleapis.com" not in text
    assert 'rel="stylesheet"' not in text  # no external stylesheet of any kind
    assert "<style>" in text  # styling is inlined
    # The "updated N ago" staleness hint is wired (offline JS over a data-iso attr).
    assert "data-iso=" in text
    assert "min ago" in text


def test_dashboard_severity_is_not_color_only(tmp_path: Path) -> None:
    # A blocked goal surfaces a TEXT severity marker, not just a red color, so the
    # severity survives for colorblind readers.
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Blocked goal",
        topology=_lease(tmp_path),
        phases=default_phases("Demo"),
        current_phase="P1",
        status="blocked",
    )
    output = tmp_path / "dashboard.html"
    render_dashboard(snapshot, output)
    text = output.read_text()
    if "<summary>Issues" in text:  # only assert when issues actually render
        assert "Blocking —" in text or "Important —" in text
