from goals.decisions import build_decision_context, explain_decision, render_decision_explanation
from goals.models import (
    DecisionOption,
    GoalSnapshot,
    JudgementRecord,
    PersonalizationContext,
    WorktreeLease,
)
from goals.runtime import default_phases
from goals.user_memory import (
    add_preference,
    build_goal_memory_digest,
    build_personalization_context,
    forget_preference,
    load_observations,
    load_preferences,
    observations_path,
    preferences_from_insights,
    preferences_path,
    record_interview_answers,
    record_observation,
    unreadable_observation_lines,
)
from goals.user_memory import goals_home, mark_interview_prompted


def test_add_preference_writes_editable_markdown(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    add_preference("communication", "Prefer concise explanations with direct tradeoffs.")

    text = preferences_path().read_text(encoding="utf-8")
    assert "## communication" in text
    assert "- Prefer concise explanations with direct tradeoffs." in text
    # Round-trips through the parser.
    prefs = load_preferences()
    assert len(prefs) == 1
    assert prefs[0].area == "communication"
    # Confirmed preferences steer auto-execution.
    assert "Prefer concise explanations" in build_personalization_context().summary


def test_add_preference_is_idempotent(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    add_preference("workflow", "Run tests before summaries.")
    add_preference("workflow", "Run tests before summaries.")

    assert len(load_preferences()) == 1


def test_hand_edited_preferences_are_read(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # A human writes the file directly — no Goals command involved.
    path.write_text(
        "# Your Goals preferences\n\n"
        "## risk\n"
        "- Ask before anything irreversible.\n"
        "- Decide reversible local changes yourself.\n",
        encoding="utf-8",
    )

    prefs = load_preferences()
    assert [p.text for p in prefs] == [
        "Ask before anything irreversible.",
        "Decide reversible local changes yourself.",
    ]
    assert all(p.area == "risk" for p in prefs)


def test_observation_records_context_not_cause(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    record_observation(
        goal_id="add auth",
        area="decision",
        choice="store sessions in Redis",
        context="sessions must be shared across instances",
    )

    line = observations_path().read_text(encoding="utf-8")
    assert "goal:add-auth" in line
    assert "chose: store sessions in Redis" in line
    assert "when: sessions must be shared across instances" in line
    # No fabricated reason when none was given.
    assert "because" not in line.lower()
    assert "- you said:" not in line  # the rendered field, not the header legend

    obs = load_observations()
    assert len(obs) == 1
    assert obs[0].provenance == "observed"
    assert obs[0].note == ""


def test_observation_keeps_user_words_as_stated_note(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    record_observation(
        goal_id="g1",
        area="risk",
        choice="a local file over a database",
        context="throwaway prototype",
        note="I don't want to manage a server",
        stated=True,  # explicitly the user's own words
    )

    obs = load_observations()[0]
    assert obs.note == "I don't want to manage a server"
    assert obs.provenance == "stated"
    assert "you said: I don't want to manage a server" in observations_path().read_text(
        encoding="utf-8"
    )


def test_recorded_rationale_is_not_attributed_to_user(monkeypatch, tmp_path) -> None:
    # A note WITHOUT stated=True (e.g. agent-recorded --why) must not be rendered
    # as the user's words — that would fabricate attribution.
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    record_observation(goal_id="g1", choice="Redis", note="needs to survive restarts")

    obs = load_observations()[0]
    assert obs.provenance == "observed"
    text = observations_path().read_text(encoding="utf-8")
    assert "- note: needs to survive restarts" in text
    assert "- you said:" not in text  # the rendered field, not the header legend


def test_observation_round_trips_adversarial_text(monkeypatch, tmp_path) -> None:
    # Free-form fields contain the field delimiters themselves; must round-trip.
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    record_observation(
        goal_id="g1",
        area="decision",
        choice="use A — when: never · really",
        context="migrate DB? (you said: maybe)",
        note='I said "x") and · stuff — when: now',
        stated=True,
    )

    obs = load_observations()
    assert len(obs) == 1
    assert obs[0].choice == "use A — when: never · really"
    assert obs[0].context == "migrate DB? (you said: maybe)"
    assert obs[0].note == 'I said "x") and · stuff — when: now'
    assert obs[0].provenance == "stated"


def test_observations_do_not_steer_other_goals(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    record_observation(goal_id="g1", choice="use Redis", context="needed shared sessions")

    # A goal-scoped observation never becomes a standing preference on its own.
    assert build_personalization_context().summary == "No user preference memory recorded yet."
    assert load_preferences() == []


def test_digest_scopes_to_goal_and_offers_promotion(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    # Same choice recurs across two distinct goals -> a promotion candidate.
    record_observation(goal_id="g1", area="workflow", choice="write tests first")
    record_observation(goal_id="g2", area="workflow", choice="write tests first")

    digest = build_goal_memory_digest("g2")
    assert "In this goal you decided" in digest
    assert "Seen across several goals — promote to a standing preference?" in digest
    assert "write tests first" in digest
    assert 'goals user record "write tests first" --area workflow' in digest
    # Not yet a standing preference (must be confirmed).
    assert "Standing preferences I'll apply" not in digest


def test_digest_drops_candidate_once_confirmed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    record_observation(goal_id="g1", area="workflow", choice="write tests first")
    record_observation(goal_id="g2", area="workflow", choice="write tests first")
    add_preference("workflow", "write tests first")

    digest = build_goal_memory_digest("g2")
    assert "promote to a standing preference" not in digest
    assert "Standing preferences I'll apply to future goals" in digest


def test_digest_empty_when_nothing_recorded(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    assert build_goal_memory_digest("demo") == ""


def test_interview_prompt_dedup_uses_markdown_not_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    assert mark_interview_prompted("demo") is True  # first time -> show it
    assert mark_interview_prompted("demo") is False  # already prompted -> skip

    # The bookkeeping lives as an HTML comment in the Markdown log; no JSON file.
    assert "<!-- goals:prompted goal:demo -->" in observations_path().read_text()
    assert not (goals_home() / "user" / "state.json").exists()
    assert not any(goals_home().rglob("*.json"))
    # And the marker is not parsed as an observation.
    assert load_observations() == []


def test_interview_answers_mark_goal_and_skip_reprompt(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    record_interview_answers(
        "demo",
        ["Prefer small reversible changes.", "Ask earlier.", "Be concise."],
    )

    # Having answered, the post-goal prompt should not fire again for that goal.
    assert mark_interview_prompted("demo") is False
    assert not any(goals_home().rglob("*.json"))


def test_interview_answers_become_preferences(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    prefs = record_interview_answers(
        "demo",
        [
            "Prefer small reversible changes.",  # -> risk (reversible)
            "Ask earlier when product direction changes.",  # -> decision (ask)
            "Explain tradeoffs without long background.",  # -> communication (explain)
        ],
    )

    assert len(prefs) == 3
    # Area is inferred from the answer's content, not its position.
    by_text = {p.text: p.area for p in prefs}
    assert by_text["Prefer small reversible changes."] == "risk"
    assert by_text["Ask earlier when product direction changes."] == "decision"
    assert by_text["Explain tradeoffs without long background."] == "communication"


def test_interview_area_falls_back_when_no_signal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    prefs = record_interview_answers("g", ["Mauve is nice", "Whatever works", "No strong view"])
    assert {p.area for p in prefs} == {"decision"}  # neutral fallback, not a fake spread


def test_observations_tolerate_hyphen_handedit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    path = observations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # A human edits with hyphens instead of the · separators.
    path.write_text(
        "# Goals observations (append-only)\n"
        "- 2026-06-24 - goal:g1 - [decision] - chose: use Postgres\n"
        "  - when: needed transactions\n",
        encoding="utf-8",
    )

    obs = load_observations()
    assert len(obs) == 1
    assert obs[0].choice == "use Postgres"
    assert obs[0].context == "needed transactions"
    assert unreadable_observation_lines() == []  # the hyphen edit is understood, not lost


def test_unparseable_observation_lines_are_surfaced_not_dropped(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    path = observations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Goals observations (append-only)\n"
        "- 2026-06-24 · goal:g1 · [decision] · chose: use Redis\n"
        "- this line got mangled by a hand edit\n",
        encoding="utf-8",
    )

    # The good line still parses; the broken one is reported rather than vanishing.
    assert [o.choice for o in load_observations()] == ["use Redis"]
    assert unreadable_observation_lines() == ["- this line got mangled by a hand edit"]


def test_forget_preference_removes_matching_bullet(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    add_preference("workflow", "Run tests before summaries.")
    add_preference("communication", "Be concise.")

    removed = forget_preference("tests before")
    assert removed == ["Run tests before summaries."]  # returns what it dropped
    remaining = [p.text for p in load_preferences()]
    assert remaining == ["Be concise."]


def test_import_insights_adds_preferences(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    added = preferences_from_insights(
        "- User tends to choose reversible local changes first.\n"
        "- User dislikes broad rewrites without evidence."
    )

    assert len(added) == 2
    assert len(load_preferences()) == 2


def test_judgement_capture_writes_observation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    from goals.decision_workflows import _record_user_judgement_signal

    warning = _record_user_judgement_signal(
        "G1",
        JudgementRecord(
            question="Where should sessions live?",
            choice="Redis",
            rationale="they must survive a restart",
            decided_by="user",
        ),
    )

    assert warning == ""
    obs = load_observations()
    assert len(obs) == 1
    assert obs[0].goal_id == "G1"
    assert obs[0].choice == "Redis"
    assert obs[0].context == "Where should sessions live?"
    assert obs[0].note == "they must survive a restart"
    # --why is recorded rationale, not a verified user quote: stays "observed".
    assert obs[0].provenance == "observed"
    assert "- you said:" not in observations_path().read_text(encoding="utf-8")


def test_judgement_capture_carries_structure(monkeypatch, tmp_path) -> None:
    # Workstream A: area is inferred (not the old constant "decision"), and
    # reversibility + phase are carried through and round-trip.
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    from goals.decision_workflows import _record_user_judgement_signal

    _record_user_judgement_signal(
        "G1",
        JudgementRecord(
            question="Is it safe to reset everything?",
            choice="drop and recreate",
            decided_by="user",
            reversible=False,
            phase_id="P3",
        ),
    )

    obs = load_observations()[0]
    assert obs.area == "risk"  # inferred from "safe", not the old constant "decision"
    assert obs.reversible is False
    assert obs.phase_id == "P3"
    text = observations_path().read_text(encoding="utf-8")
    assert "- reversible: no" in text
    assert "- phase: P3" in text


def test_observation_structure_round_trips(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    record_observation(
        goal_id="g1",
        area="risk",
        choice="a local file over a database",
        context="throwaway prototype",
        reversible=True,
        phase_id="P2",
    )
    obs = load_observations()[0]
    assert obs.reversible is True
    assert obs.phase_id == "P2"


def test_reworded_preference_drops_promotion_candidate(monkeypatch, tmp_path) -> None:
    # Workstream B: confirming a reworded preference under a *different* area than
    # the digest suggested still silences the candidate (the F1 bug from dogfood).
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    from goals.decision_workflows import _record_user_judgement_signal

    for goal in ("g1", "g2"):
        _record_user_judgement_signal(
            goal,
            JudgementRecord(question="Testing approach?", choice="pytest with fixtures",
                            decided_by="user"),
        )
    # Candidate is offered before confirmation.
    assert "pytest with fixtures" in build_goal_memory_digest("g2")

    # User confirms it reworded and under a different area than the suggestion.
    add_preference("workflow", "Use pytest with fixtures for tests")

    digest = build_goal_memory_digest("g2")
    assert "promote to a standing preference" not in digest
    assert "Use pytest with fixtures for tests" in digest  # shown as a standing pref


def test_agent_decisions_are_not_recorded_as_user_memory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    from goals.decision_workflows import _record_user_judgement_signal

    _record_user_judgement_signal(
        "G1",
        JudgementRecord(question="q", choice="x", decided_by="agent"),
    )

    assert load_observations() == []


def test_legacy_json_store_is_migrated_not_lost(monkeypatch, tmp_path) -> None:
    import json

    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    user_dir = goals_home() / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    # Simulate a pre-Markdown install: active claim + an episodic event log.
    (user_dir / "memory.json").write_text(
        json.dumps(
            {
                "claims": [
                    {"area": "communication", "statement": "Be concise.", "status": "active"},
                    {"area": "risk", "statement": "An old candidate.", "status": "candidate"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (user_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")

    prefs = load_preferences()

    # Active claim is preserved as a preference; candidate is not promoted.
    assert [(p.area, p.text) for p in prefs] == [("communication", "Be concise.")]
    # Legacy files are kept as .bak (no silent data loss), originals gone.
    assert (user_dir / "memory.json.bak").exists()
    assert (user_dir / "events.jsonl.bak").exists()
    assert not (user_dir / "memory.json").exists()
    # Migration is idempotent and leaves a discoverable note.
    assert "Imported 1 preference" in preferences_path().read_text(encoding="utf-8")
    assert len(load_preferences()) == 1


def test_personalization_does_not_hide_high_risk_decision(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Pick storage",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Pick storage"),
        current_phase="P1",
    )
    personalization = PersonalizationContext(
        summary="risk: prefer reversible choices",
        claim_ids=["UPC-demo"],
        guidance=["risk: prefer reversible choices"],
        confidence=0.9,
    )
    context = build_decision_context(snapshot, personalization)
    decision = explain_decision(
        title="Choose storage",
        plain_summary="Pick durable storage.",
        why_it_matters="This affects migration risk.",
        recommendation="Use local file",
        options=[
            DecisionOption(
                label="Local file",
                explanation="Simple and reversible.",
                reversible=True,
                risk="low",
            ),
            DecisionOption(
                label="Production database",
                explanation="Higher setup risk.",
                reversible=False,
                risk="high",
            ),
        ],
        confidence=0.7,
        context=context,
    )

    explanation = render_decision_explanation(decision, context)

    assert explanation.surfaced_to_user is True
    assert "At least one option is high risk." in explanation.reason_for_surface
    assert "User memory: risk: prefer reversible choices" in explanation.markdown
