from todo import TodoList


def test_add_task() -> None:
    todos = TodoList()
    task = todos.add("Write release notes")
    assert task.title == "Write release notes"
    assert todos.all() == [task]
