from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    title: str
    done: bool = False
    tags: list[str] = field(default_factory=list)


class TodoList:
    def __init__(self) -> None:
        self._tasks: list[Task] = []

    def add(self, title: str) -> Task:
        task = Task(title=title)
        self._tasks.append(task)
        return task

    def all(self) -> list[Task]:
        return list(self._tasks)

    def mark_done(self, title: str) -> Task:
        """Mark the first task with this title as done and return it.

        Raises ValueError if no task has that title.
        """
        for task in self._tasks:
            if task.title == title:
                task.done = True
                return task
        raise ValueError(f"no task titled {title!r}")
