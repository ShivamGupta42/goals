from todo import TodoList


def test_add_task() -> None:
    todos = TodoList()
    task = todos.add("Write release notes")
    assert task.title == "Write release notes"
    assert todos.all() == [task]


def test_remove_task_by_title() -> None:
    todos = TodoList()
    keep = todos.add("Buy milk")
    todos.add("Write release notes")
    todos.remove("Write release notes")
    assert todos.all() == [keep]


def test_remove_deletes_all_tasks_with_that_title() -> None:
    todos = TodoList()
    todos.add("Dup")
    todos.add("Dup")
    todos.remove("Dup")
    assert todos.all() == []


def test_remove_missing_title_raises_key_error() -> None:
    todos = TodoList()
    todos.add("Buy milk")
    try:
        todos.remove("Nope")
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")
    assert len(todos.all()) == 1
