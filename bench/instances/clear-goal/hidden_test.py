"""Hidden check for clear-goal (also used by new-session). Never copied into a run.

It asserts only what the goal sentence pins down. What happens with duplicate
titles, a missing title or a different letter case is left to the agent.
"""

from todo import TodoList


def test_remove_deletes_the_task_with_that_title() -> None:
    todos = TodoList()
    todos.add("Write release notes")
    todos.add("Ship it")
    todos.remove("Write release notes")
    assert [task.title for task in todos.all()] == ["Ship it"]


def test_add_still_works() -> None:
    todos = TodoList()
    task = todos.add("Write release notes")
    assert task.title == "Write release notes"
    assert todos.all() == [task]
