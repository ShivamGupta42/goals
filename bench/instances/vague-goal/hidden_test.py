"""Leak marker: goals-bench-hidden-check-marker-6d1f. Holds a check, so it is never copied into a run.

Hidden check for vague-goal part B. Never copied into a run.

It asserts only what the scripted reply asks for: mark_done(title) marks that
task as done, and the existing API keeps working.
"""

from todo import TodoList


def test_mark_done_marks_only_that_task() -> None:
    todos = TodoList()
    todos.add("Write release notes")
    todos.add("Ship it")
    todos.mark_done("Write release notes")
    done = {task.title: task.done for task in todos.all()}
    assert done == {"Write release notes": True, "Ship it": False}


def test_add_still_works() -> None:
    todos = TodoList()
    task = todos.add("Write release notes")
    assert task.title == "Write release notes"
    assert task.done is False
    assert todos.all() == [task]
