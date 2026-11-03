"""Event and event bus.

Every message between modules is an Event with a type, a timestamp, a source and a
reason. Modules never call each other directly: they subscribe to event types and
publish new events. The bus keeps an append-only log, so any run can be inspected
or compared against a replay of itself.

Ordering rule: events are processed FIFO. An event published while another is being
handled is queued behind it, never handled re-entrantly. This keeps causality simple:
nothing can react to an event before the event that caused it has finished.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

# Event types, named as in the muniQuant Event-Based Trading System Overview.
MARKET_TICK = "MARKET_TICK"
BAR_CLOSED = "BAR_CLOSED"
SIGNAL_CREATED = "SIGNAL_CREATED"
SIGNAL_REJECTED = "SIGNAL_REJECTED"
RISK_PASSED = "RISK_PASSED"
RISK_FAILED = "RISK_FAILED"
ORDER_SUBMITTED = "ORDER_SUBMITTED"
ORDER_FILLED = "ORDER_FILLED"
PNL_UPDATED = "PNL_UPDATED"

ALL_TYPES = (MARKET_TICK, BAR_CLOSED, SIGNAL_CREATED, SIGNAL_REJECTED, RISK_PASSED,
             RISK_FAILED, ORDER_SUBMITTED, ORDER_FILLED, PNL_UPDATED)


@dataclass(frozen=True)
class Event:
    type: str
    ts: int                      # market time of the tick that caused this event
    source: str                  # module that published it
    reason: str                  # why it exists, in words
    payload: dict[str, Any] = field(default_factory=dict)
    seq: int = -1                # position in the bus log, set on publish
    parent: int | None = None    # seq of the event that caused this one

    def __post_init__(self):
        if self.type not in ALL_TYPES:
            raise ValueError(f"unknown event type {self.type!r}")
        if not self.source or not self.reason:
            raise ValueError("every event needs a source and a reason")


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._queue: deque[Event] = deque()
        self.log: list[Event] = []
        self._dispatching = False

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._subs[event_type].append(handler)

    def publish(self, type: str, ts: int, source: str, reason: str,
                payload: dict[str, Any] | None = None, parent: Event | None = None) -> Event:
        ev = Event(type, ts, source, reason, dict(payload or {}),
                   seq=len(self.log), parent=None if parent is None else parent.seq)
        self.log.append(ev)
        self._queue.append(ev)
        if not self._dispatching:
            self._drain()
        return ev

    def _drain(self) -> None:
        self._dispatching = True
        try:
            while self._queue:
                ev = self._queue.popleft()
                for h in self._subs.get(ev.type, []):
                    h(ev)
        finally:
            self._dispatching = False

    def of_type(self, *types: str) -> list[Event]:
        return [e for e in self.log if e.type in types]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for e in self.log:
            out[e.type] += 1
        return dict(out)
