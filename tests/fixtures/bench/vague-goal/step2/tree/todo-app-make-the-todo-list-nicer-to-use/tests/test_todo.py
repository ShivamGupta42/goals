from todo import TodoList


def test_add_task() -> None:
    todos = TodoList()
    task = todos.add("Write release notes")
    assert task.title == "Write release notes"
    assert todos.all() == [task]


def test_mark_done() -> None:
    todos = TodoList()
    todos.add("Write release notes")
    task = todos.mark_done("Write release notes")
    assert task.done is True
    assert todos.all()[0].done is True
