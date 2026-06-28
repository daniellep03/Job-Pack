"""
Event Bus — implements two patterns at once:
  - GoF Observer: EventBus is the Subject, subscribers are Observers.
  - EIP Publish-Subscribe: publishers and subscribers only ever know about
    the bus, never about each other.

This is what decouples the generation pipeline (pipeline.py / state_machine.py)
from the WebSocket layer (sockets.py) and the audit trail (audit.py) — neither
of those is ever imported by the pipeline.
"""

from collections import defaultdict
from typing import Callable, DefaultDict, List


class EventBus:
    def __init__(self):
        self._subscribers: DefaultDict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable) -> None:
        self._subscribers[event_name].append(handler)

    def publish(self, event_name: str, **payload) -> None:
        for handler in self._subscribers.get(event_name, []):
            handler(**payload)


# Single process-wide bus. Fine for a single-dyno Flask deployment;
# swap for a Redis-backed bus if this ever needs to scale to multiple workers.
bus = EventBus()
