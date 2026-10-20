"""Small synchronous event bus for gameplay feedback and future audio."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable


class Events:
    def __init__(self) -> None:
        self.listeners: dict[str, list[Callable[..., None]]] = defaultdict(list)
        self.recent: deque[tuple[str, dict]] = deque(maxlen=5)

    def subscribe(self, name: str, callback: Callable[..., None]) -> None:
        """Register a callback for a named event."""
        self.listeners[name].append(callback)

    def emit(self, name: str, **data: object) -> None:
        """Deliver an event immediately and retain it for debugging."""
        self.recent.append((name, data))
        for callback in self.listeners[name]:
            callback(**data)
