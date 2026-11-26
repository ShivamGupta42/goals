import random

from todo import TodoList


def test_remove_matches_a_plain_list_model_over_random_operations() -> None:
    """Hunt for hidden bugs: compare TodoList against a simple list model.

    Random add/remove sequences (including repeated and case-varied titles)
    must leave both with the same titles in the same order, and remove must
    report True/False exactly when the model had a match.
    """
    rng = random.Random(1234)
    names = ["a", "b", "Milk", "milk", ""]
    for _ in range(300):
        todos = TodoList()
        model: list[str] = []
        for _ in range(60):
            name = rng.choice(names)
            if rng.random() < 0.6:
                todos.add(name)
                model.append(name)
            else:
                expected = name in model
                if expected:
                    model.remove(name)
                assert todos.remove(name) is expected
            assert [t.title for t in todos.all()] == model
