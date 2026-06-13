from goals.brief import build_goal_brief, render_goal_brief
from goals.decisions import explain_decision
from goals.models import (
    DecisionOption,
    Evidence,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    Phase,
    PhaseStatus,
    WorktreeLease,
)


def test_goal_brief_surfaces_only_user_worthy_items(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Add tags to tasks",
        definition_of_done=["Tags work and tests pass."],
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
                goal="Find storage constraints.",
                status=PhaseStatus.ACCEPTED,
                evidence=Evidence(
                    changed_files=["src/db.py"],
                    checks_run=["pytest"],
                    acceptance_met=["Storage inspected."],
                    known_gaps=["Migration order is unclear."],
                    confidence=0.9,
                ),
                reviews=[
                    GateResult(
                        gate_id="phase-review",
                        verdict=GateVerdict.PASS,
                        summary="ok",
                    )
                ],
            ),
            Phase(
                phase_id="P2",
                title="Implement tags",
                goal="Add tags.",
                status=PhaseStatus.NEEDS_REVIEW,
                evidence=Evidence(
                    changed_files=["db/migrations/0102_add_tags.py"],
                    checks_run=["pytest"],
                    acceptance_met=["Tags work."],
                    confidence=0.9,
                ),
            ),
        ],
        current_phase="P2",
        decisions=[
            explain_decision(
                title="Migration approval",
                plain_summary="Choose whether to allow a data migration.",
                why_it_matters="Data migrations can be hard to undo.",
                recommendation="Avoid migration until approved.",
                options=[
                    DecisionOption(
                        label="Allow migration",
                        explanation="Change stored data shape.",
                        risk="high",
                        reversible=False,
                    ),
                    DecisionOption(
                        label="Avoid migration",
                        explanation="Use existing storage.",
                        risk="low",
                        reversible=True,
                    ),
                ],
                confidence=0.8,
                priority="blocking",
            ),
            explain_decision(
                title="Button label",
                plain_summary="Choose the tag button label.",
                why_it_matters="This is copy only.",
                recommendation="Use Tags.",
                options=[
                    DecisionOption(
                        label="Tags",
                        explanation="Short label.",
                        risk="low",
                        reversible=True,
                    )
                ],
                confidence=0.9,
                priority="later",
            ),
        ],
    )

    brief = build_goal_brief(snapshot)
    rendered = render_goal_brief(brief)

    assert brief.waiting_on == "you"
    assert [action.title for action in brief.user_actions] == ["Migration approval"]
    assert any(action.source == "merge" for action in brief.agent_actions)
    assert "Choose the tag button label" not in rendered
    assert "What Needs Your Answer" in rendered
    assert "What the Agent Can Do Next" in rendered
    assert "1/2 step(s) accepted" in rendered


def test_goal_brief_keeps_repair_work_with_agent(tmp_path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Prepare customer brief",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[
            Phase(
                phase_id="P1",
                title="Draft",
                goal="Draft the brief.",
                status=PhaseStatus.NEEDS_REVIEW,
                evidence=Evidence(
                    acceptance_not_met=["Sources not checked."],
                    confidence=0.4,
                ),
            )
        ],
        current_phase="P1",
    )

    brief = build_goal_brief(snapshot)

    assert brief.waiting_on == "agent"
    assert brief.user_actions == []
    assert brief.agent_actions
    assert "Nothing important needs your answer" in brief.summary
