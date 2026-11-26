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

    def remove(self, title: str) -> bool:
        """Delete the first task whose title matches exactly.

        Returns True if a task was removed, False if no task had that title.
        """
        for index, task in enumerate(self._tasks):
            if task.title == title:
                del self._tasks[index]
                return True
        return False
