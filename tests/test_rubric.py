"""The rubric is the only place gate facts become a human category, and the kernel
must stay free of that vocabulary.
"""

from pathlib import Path

from goals.issues import _GATE_CATEGORY_ACTION
from goals.models import GateFactType, GateFinding, GateFindingCategory
from goals.rubric import category_for, representative_category


def test_every_fact_maps_to_a_category() -> None:
    # No fact may be left unmapped — category_for must total over the enum.
    for fact in GateFactType:
        assert isinstance(category_for(fact), GateFindingCategory)


def test_every_category_has_a_next_step_action() -> None:
    # If a category is added without a plain-language next step, goals check would
    # silently fall back to the generic action — catch that omission here.
    for category in GateFindingCategory:
        assert category in _GATE_CATEGORY_ACTION


def test_signal_carrying_facts_map_as_designed() -> None:
    assert category_for(GateFactType.CHECK_FAILED) is GateFindingCategory.BUG
    assert category_for(GateFactType.ACCEPTANCE_NOT_MET) is GateFindingCategory.GAP
    assert category_for(GateFactType.NO_PASSING_CHECK) is GateFindingCategory.VERIFICATION_MISS
    assert category_for(GateFactType.MISSING_FALSIFIER) is GateFindingCategory.VERIFICATION_MISS


def test_representative_category_precedence() -> None:
    def finding(fact: GateFactType) -> GateFinding:
        # ref is harmless on non-ref facts and required on ref-bearing ones.
        return GateFinding(fact_type=fact, message="x", ref="R-1")

    # BUG outranks GAP outranks VERIFICATION_MISS, regardless of order.
    bug_and_miss = [finding(GateFactType.NO_PASSING_CHECK), finding(GateFactType.CHECK_FAILED)]
    assert representative_category(bug_and_miss) is GateFindingCategory.BUG

    gap_and_miss = [finding(GateFactType.AMBIGUOUS), finding(GateFactType.ACCEPTANCE_NOT_MET)]
    assert representative_category(gap_and_miss) is GateFindingCategory.GAP

    assert representative_category([]) is None


def test_kernel_does_not_name_the_rubric() -> None:
    # gates.py emits facts only; the category vocabulary lives in the rubric/presentation.
    # (A docstring may *reference* the rubric to explain the seam; what's forbidden is
    # importing or using it.)
    gates_src = (Path(__file__).resolve().parents[1] / "src" / "goals" / "gates.py").read_text()
    assert "GateFindingCategory" not in gates_src
    assert "category_for" not in gates_src
    assert "from goals.rubric" not in gates_src
    assert "import rubric" not in gates_src
