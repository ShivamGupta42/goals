from goals.decisions import explain_decision
from goals.gates import review_phase
from goals.models import DecisionOption, Evidence, GateVerdict, Phase


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
