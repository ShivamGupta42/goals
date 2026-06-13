from goals.decisions import (
    build_decision_brief,
    build_decision_context,
    explain_decision,
    render_decision_brief,
    render_decision_explanation,
)
from goals.gates import review_phase
from goals.models import (
    DecisionOption,
    Evidence,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    Phase,
    PhaseStatus,
    SourceClaim,
    SourceRecord,
    WorktreeLease,
)


def test_phase_review_requires_evidence() -> None:
    result = review_phase(Phase(phase_id="P1", title="Step", goal="Do it"))
    assert result.verdict == GateVerdict.FAIL
    assert result.p0


def test_phase_review_blocks_after_rf_cap() -> None:
    result = review_phase(
        Phase(phase_id="P1", title="Step", goal="Do it"), attempt=3, max_attempts=3
    )
    assert result.verdict == GateVerdict.BLOCKED
    assert result.attempts == 3
    assert "cap reached" in result.summary


def test_phase_review_passes_with_strong_evidence() -> None:
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(checks_run=["pytest"], acceptance_met=["done"], confidence=0.9),
    )
    result = review_phase(phase)
    assert result.verdict == GateVerdict.PASS


def test_decision_explainer_preserves_risk_and_reversibility() -> None:
    decision = explain_decision(
        title="Choose database",
        plain_summary="Pick where the app stores data.",
        why_it_matters="This affects setup and future scale.",
        recommendation="SQLite now",
        options=[
            DecisionOption(
                label="SQLite now",
                explanation="A local file database.",
                tradeoffs=["Easy now, may migrate later."],
                reversible=True,
                reversal_plan="Use a storage adapter.",
                risk="low",
            )
        ],
        confidence=0.8,
    )
    assert decision.options[0].reversible is True
    assert decision.options[0].risk == "low"
    assert "SQLite" in decision.suggested_reply


def test_decision_explainer_uses_goal_history_context(tmp_path) -> None:
    phase = Phase(
        phase_id="P1",
        title="Inspect storage",
        goal="Find the storage shape",
        status=PhaseStatus.ACCEPTED,
        evidence=Evidence(
            changed_files=["src/db.py"],
            checks_run=["pytest"],
            known_gaps=["Migration order is unclear."],
            confidence=0.8,
            notes="Storage is file-backed today.",
        ),
        reviews=[GateResult(gate_id="phase-review", verdict=GateVerdict.PASS, summary="ok")],
    )
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add tags to tasks",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[phase],
        current_phase=None,
        learnings=["Use reversible storage changes first."],
        sources=[
            SourceRecord(
                source_id="SRC-1",
                title="Support ticket",
                source_type="document",
                summary="Users asked for tag filtering.",
            )
        ],
        source_claims=[
            SourceClaim(
                claim="Users asked for tag filtering.",
                source_ids=["SRC-1"],
                confidence=0.8,
            )
        ],
    )
    context = build_decision_context(snapshot)
    decision = explain_decision(
        title="Choose tag storage",
        plain_summary="Pick where task tags should live.",
        why_it_matters="This affects migration risk.",
        recommendation="Store tags in the existing task file",
        options=[
            DecisionOption(
                label="Existing file",
                explanation="No migration.",
                tradeoffs=["Less scalable."],
                reversible=True,
                risk="low",
            ),
            DecisionOption(
                label="New migration",
                explanation="Add a table.",
                tradeoffs=["Migration order risk."],
                reversible=False,
                risk="high",
            ),
        ],
        confidence=0.74,
        context=context,
        technical_details="Existing file avoids migration ordering issues.",
    )
    explanation = render_decision_explanation(decision, context, level="technical")

    assert explanation.surfaced_to_user is True
    assert "At least one option is high risk." in explanation.reason_for_surface
    assert "Checks run: pytest" in explanation.markdown
    assert "file:src/db.py" in explanation.markdown
    assert "Migration order is unclear." in explanation.markdown
    assert "Users asked for tag filtering." in explanation.markdown


def test_low_risk_reversible_decision_can_stay_with_agent(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Prepare a customer brief",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[],
        current_phase=None,
    )
    context = build_decision_context(snapshot)
    decision = explain_decision(
        title="Choose memo heading",
        plain_summary="Pick a heading for the brief.",
        why_it_matters="It affects presentation only.",
        recommendation="Use a plain heading",
        options=[
            DecisionOption(
                label="Plain heading",
                explanation="Easy to change later.",
                reversible=True,
                risk="low",
            )
        ],
        confidence=0.9,
        context=context,
        priority="later",
    )
    explanation = render_decision_explanation(decision, context, level="basic")

    assert explanation.surfaced_to_user is False
    assert "does not need to interrupt" not in explanation.markdown
    assert "agent can choose" in explanation.reason_for_surface


def test_decision_brief_summarizes_only_user_worthy_decisions(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add tags to tasks",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Inspect storage",
                goal="Find the storage shape",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    changed_files=["src/db.py"],
                    checks_run=["pytest"],
                    known_gaps=["Migration order is unclear."],
                    acceptance_met=["Storage inspected."],
                    confidence=0.8,
                    notes="Storage is file-backed today.",
                ),
                reviews=[
                    GateResult(gate_id="phase-review", verdict=GateVerdict.PASS, summary="ok")
                ],
            )
        ],
        current_phase="P2",
        decisions=[
            explain_decision(
                title="Choose tag storage",
                plain_summary="Pick where task tags should live.",
                why_it_matters="This affects migration risk.",
                recommendation="Store tags in the existing task file",
                options=[
                    DecisionOption(
                        label="Existing file",
                        explanation="No migration needed.",
                        reversible=True,
                        risk="low",
                    ),
                    DecisionOption(
                        label="New migration",
                        explanation="More structured.",
                        tradeoffs=["Migration ordering risk."],
                        reversible=False,
                        risk="high",
                    ),
                ],
                confidence=0.74,
                priority="blocking",
                technical_details="Migration order has to be coordinated.",
            ),
            explain_decision(
                title="Dashboard label wording",
                plain_summary="Choose label wording for the dashboard.",
                why_it_matters="It affects presentation only.",
                recommendation="Use the shorter label.",
                options=[
                    DecisionOption(
                        label="Short label",
                        explanation="Easy to scan.",
                        reversible=True,
                        risk="low",
                    )
                ],
                confidence=0.9,
                priority="later",
            ),
        ],
    )

    brief = build_decision_brief(snapshot)
    rendered = render_decision_brief(brief)

    assert brief.waiting_on_user is True
    assert len(brief.user_decisions) == 1
    assert brief.agent_handled_count == 1
    assert brief.user_decisions[0].highest_risk == "high"
    assert brief.user_decisions[0].all_options_reversible is False
    assert "continue P2" in brief.user_decisions[0].what_happens_next
    assert "What Needs Your Answer" in rendered
    assert "Suggested reply: `I choose: Store tags in the existing task file`" in rendered
    assert "1 routine/reversible choice(s) can stay with the agent." in rendered
    assert "Dashboard label wording" not in rendered
