from goals.models import Decision as ModelDecision
from goals.models import GateResult as ModelGateResult
from goals.models import GoalSnapshot as ModelGoalSnapshot
from goals.schemas.core import GoalSnapshot
from goals.schemas.decisions import Decision
from goals.schemas.gates import GateResult


def test_schema_modules_reexport_model_types() -> None:
    assert GoalSnapshot is ModelGoalSnapshot
    assert Decision is ModelDecision
    assert GateResult is ModelGateResult
