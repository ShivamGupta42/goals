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
)


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
    assert "you said" not in line

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
    )

    obs = load_observations()[0]
    assert obs.note == "I don't want to manage a server"
    assert obs.provenance == "stated"
    assert 'you said: "I don\'t want to manage a server"' in observations_path().read_text(
        encoding="utf-8"
    )


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


def test_interview_answers_become_preferences(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    prefs = record_interview_answers(
        "demo",
        [
            "Prefer small reversible changes.",
            "Ask earlier when product direction changes.",
            "Explain tradeoffs without long background.",
        ],
    )

    assert len(prefs) == 3
    assert {p.area for p in prefs} == {"decision", "workflow", "communication"}
    assert any("reversible" in p.text for p in load_preferences())


def test_forget_preference_removes_matching_bullet(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    add_preference("workflow", "Run tests before summaries.")
    add_preference("communication", "Be concise.")

    removed = forget_preference("tests before")
    assert removed == 1
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
    assert obs[0].note == "they must survive a restart"  # user's words, not inferred
    assert obs[0].provenance == "stated"


def test_agent_decisions_are_not_recorded_as_user_memory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    from goals.decision_workflows import _record_user_judgement_signal

    _record_user_judgement_signal(
        "G1",
        JudgementRecord(question="q", choice="x", decided_by="agent"),
    )

    assert load_observations() == []


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
