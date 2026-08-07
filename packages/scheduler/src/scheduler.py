from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class Task:
    id: str
    dependencies: List[str]

class DeterministicScheduler:
    def order(self, tasks: List[Task]) -> List[str]:
        return [task.id for task in tasks]
