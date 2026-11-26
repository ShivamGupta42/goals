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

    def remove(self, title: str) -> None:
        """Delete every task whose title matches exactly.

        Raises KeyError if no task has that title.
        """
        remaining = [task for task in self._tasks if task.title != title]
        if len(remaining) == len(self._tasks):
            raise KeyError(title)
        self._tasks = remaining
