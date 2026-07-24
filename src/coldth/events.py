from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class EventBus:
    """In-process fan-out for Coldth's public event stream."""

    def __init__(self) -> None:
        self._sequence = 0
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def envelope(self, event_type: str, data: Any) -> dict[str, Any]:
        self._sequence += 1
        return {
            "seq": self._sequence,
            "type": event_type,
            "timestamp": utc_timestamp(),
            "data": data,
        }

    async def publish(self, event_type: str, data: Any) -> dict[str, Any]:
        event = self.envelope(event_type, data)
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)
        return event
