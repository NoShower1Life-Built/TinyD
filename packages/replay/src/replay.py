from typing import Iterable

class ReplayEngine:
    def replay(self, events: Iterable[dict]) -> list[dict]:
        return list(events)
