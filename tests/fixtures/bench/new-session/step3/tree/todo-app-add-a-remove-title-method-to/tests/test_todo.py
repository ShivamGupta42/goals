from todo import TodoList


def test_add_task() -> None:
    todos = TodoList()
    task = todos.add("Write release notes")
    assert task.title == "Write release notes"
    assert todos.all() == [task]


def test_remove_deletes_only_the_matching_task() -> None:
    todos = TodoList()
    keep = todos.add("Keep me")
    gone = todos.add("Delete me")
    assert todos.remove("Delete me") is True
    assert gone not in todos.all()
    assert todos.all() == [keep]


def test_remove_missing_title_changes_nothing() -> None:
    todos = TodoList()
    task = todos.add("Only task")
    assert todos.remove("Nope") is False
    assert todos.all() == [task]


def test_remove_only_first_of_duplicate_titles() -> None:
    todos = TodoList()
    todos.add("Dup")
    second = todos.add("Dup")
    assert todos.remove("Dup") is True
    remaining = todos.all()
    assert len(remaining) == 1
    assert remaining[0] is second


def test_remove_is_case_sensitive() -> None:
    todos = TodoList()
    task = todos.add("Milk")
    assert todos.remove("milk") is False
    assert todos.all() == [task]
