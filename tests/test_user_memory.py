from goals.decisions import build_decision_context, explain_decision, render_decision_explanation
from goals.models import (
    DecisionOption,
    GoalSnapshot,
    PersonalizationContext,
    UserMemoryEvent,
    WorktreeLease,
)
from goals.runtime import default_phases
from goals.user_memory import (
    append_user_event,
    build_goal_memory_digest,
    build_personalization_context,
    events_from_insights,
    forget_claim,
    load_user_memory,
    user_memory_path,
)


def test_user_memory_records_active_manual_claim(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    append_user_event(
        UserMemoryEvent(
            kind="manual",
            area="communication",
            summary="Prefer concise explanations with direct tradeoffs.",
            source="manual",
            confidence=0.9,
        )
    )

    memory = load_user_memory()
    assert user_memory_path().exists()
    assert len(memory.claims) == 1
    assert memory.claims[0].status == "active"
    assert memory.claims[0].area == "communication"
    context = build_personalization_context()
    assert "Prefer concise explanations" in context.summary
    assert context.claim_ids == [memory.claims[0].claim_id]


def test_user_memory_imported_insights_start_as_candidates(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    events = events_from_insights(
        "- User tends to choose reversible local changes first.\n"
        "- User dislikes broad rewrites without evidence."
    )
    for event in events:
        append_user_event(event)

    memory = load_user_memory()
    assert len(memory.claims) == 2
    assert {claim.status for claim in memory.claims} == {"candidate"}
    assert build_personalization_context().summary == "No user preference memory recorded yet."


def test_user_memory_imported_insights_dedupe_single_paste(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    events = events_from_insights(
        "- User tends to choose reversible local changes first.\n"
        "- User tends to choose reversible local changes first.\n"
    )
    for event in events:
        append_user_event(event)

    memory = load_user_memory()
    assert len(events) == 1
    assert len(memory.claims) == 1
    assert memory.claims[0].status == "candidate"


def test_user_memory_interview_derives_one_claim_per_answer(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    append_user_event(
        UserMemoryEvent(
            kind="interview",
            area="decision",
            summary="combined fallback",
            source="post_goal_interview",
            goal_id="demo",
            confidence=0.9,
            details=[
                "Prefer small reversible changes.",
                "Ask earlier when product direction changes.",
                "Explain tradeoffs without long background.",
            ],
        )
    )

    memory = load_user_memory()

    assert len(memory.claims) == 3
    assert memory.interviewed_goal_ids == ["demo"]
    assert {claim.status for claim in memory.claims} == {"active"}
    assert any("small reversible changes" in claim.statement for claim in memory.claims)
    assert all("combined fallback" not in claim.statement for claim in memory.claims)


def test_user_memory_conflicting_explicit_claims_keep_newest_active(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    append_user_event(
        UserMemoryEvent(
            kind="manual",
            area="risk",
            summary="Prefer fast choices when the change is reversible.",
            source="manual",
            confidence=0.9,
        )
    )
    memory = append_user_event(
        UserMemoryEvent(
            kind="manual",
            area="risk",
            summary="Prefer asking before risk tradeoffs even when reversible.",
            source="manual",
            confidence=0.95,
        )
    )

    active = [claim for claim in memory.claims if claim.status == "active"]
    inactive = [claim for claim in memory.claims if claim.status == "inactive"]
    assert len(active) == 1
    assert "asking before risk tradeoffs" in active[0].statement
    assert len(inactive) == 1


def test_user_memory_forget_deactivates_claim(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    memory = append_user_event(
        UserMemoryEvent(
            kind="manual",
            area="workflow",
            summary="Prefer tests before implementation summaries.",
            source="manual",
            confidence=0.9,
        )
    )
    claim_id = memory.claims[0].claim_id

    memory = forget_claim(claim_id)

    assert memory.claims[0].status == "forgotten"
    assert build_personalization_context().summary == "No user preference memory recorded yet."


def test_goal_memory_digest_empty_when_nothing_learned(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    assert build_goal_memory_digest("demo") == ""


def test_goal_memory_digest_surfaces_this_goal_and_steering(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    append_user_event(
        UserMemoryEvent(
            kind="judgement",
            area="decision",
            summary="For 'Pick storage', the user chose 'local file'.",
            source="judgement",
            goal_id="demo",
            confidence=0.6,
        )
    )
    append_user_event(
        UserMemoryEvent(
            kind="manual",
            area="communication",
            summary="Prefer concise explanations with direct tradeoffs.",
            source="manual",
            confidence=0.9,
        )
    )

    digest = build_goal_memory_digest("demo")

    assert "Goal-execution memory" in digest
    # A judgement tied to this goal is reflected back.
    assert "For 'Pick storage', the user chose 'local file'." in digest
    # An active claim is surfaced as future auto-execution steering.
    assert "Prefer concise explanations" in digest
    assert "How I'll auto-execute future goals to fit you:" in digest


def test_goal_memory_digest_scopes_judgements_to_goal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))

    append_user_event(
        UserMemoryEvent(
            kind="judgement",
            area="decision",
            summary="For 'Other goal', the user chose 'database'.",
            source="judgement",
            goal_id="other",
            confidence=0.6,
        )
    )

    digest = build_goal_memory_digest("demo")

    # No active claims and no judgements for this goal -> nothing to surface.
    assert "From this goal:" not in digest


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
