"""The five modules of the loop: market data -> strategy -> risk -> execution -> portfolio.

Each module only subscribes to the events it needs and publishes the next one.
No module holds a reference to another module.

Causality rule: an order created at tick t fills at tick t+1, at that tick's price
plus half the spread. A strategy can never trade at the price it decided on.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .core import (BAR_CLOSED, MARKET_TICK, ORDER_FILLED, ORDER_SUBMITTED, PNL_UPDATED,
                   RISK_FAILED, RISK_PASSED, SIGNAL_CREATED, Event, EventBus)


# ---------------------------------------------------------------- 1. data intake

class MarketData:
    """Turns ticks into bars of `bar_size` ticks. Publishes a bar only once it is closed."""

    def __init__(self, bus: EventBus, bar_size: int = 10) -> None:
        self.bus, self.bar_size = bus, bar_size
        self._px: list[float] = []
        bus.subscribe(MARKET_TICK, self.on_tick)

    def on_tick(self, ev: Event) -> None:
        self._px.append(ev.payload["price"])
        if len(self._px) == self.bar_size:
            p = self._px
            self.bus.publish(BAR_CLOSED, ev.ts, "market_data", f"{self.bar_size} ticks closed",
                             {"open": p[0], "high": max(p), "low": min(p), "close": p[-1]},
                             parent=ev)
            self._px = []


# ---------------------------------------------------------------- 2-3. strategy

class Strategy(Protocol):
    name: str
    def target(self, closes: list[float]) -> int | None:
        """Desired position given all closed bars so far. None = no opinion yet."""


class DoNothing:
    name = "do_nothing"
    def target(self, closes):
        return None


@dataclass
class MACross:
    """Long `size` when the fast moving average is above the slow one, short `size` below."""
    fast: int = 5
    slow: int = 20
    size: int = 10
    name: str = "ma_cross"

    def target(self, closes):
        if len(closes) < self.slow:
            return None
        f = sum(closes[-self.fast:]) / self.fast
        s = sum(closes[-self.slow:]) / self.slow
        return self.size if f > s else -self.size


class StrategyModule:
    """Wraps a Strategy. Publishes SIGNAL_CREATED only when the desired position changes."""

    def __init__(self, bus: EventBus, strategy: Strategy) -> None:
        self.bus, self.strategy = bus, strategy
        self._closes: list[float] = []
        self._last: int | None = None
        bus.subscribe(BAR_CLOSED, self.on_bar)

    def on_bar(self, ev: Event) -> None:
        self._closes.append(ev.payload["close"])
        tgt = self.strategy.target(self._closes)
        if tgt is None or tgt == self._last:
            return
        self._last = tgt
        self.bus.publish(SIGNAL_CREATED, ev.ts, self.strategy.name,
                         f"target position {tgt}", {"target": tgt}, parent=ev)


# ---------------------------------------------------------------- 4. risk

@dataclass
class RiskLimits:
    position_limit: int = 20      # max |position| after the order
    max_order: int = 25           # max |quantity| of one order
    max_drawdown: float = 50.0    # equity drop from peak (currency) that halts trading


class RiskModule:
    """Turns a target into an order quantity and approves or rejects it.

    Once drawdown exceeds the limit the module halts: it flattens the position once and
    rejects every later signal. `committed` is the position after all approved orders fill.
    """

    def __init__(self, bus: EventBus, limits: RiskLimits) -> None:
        self.bus, self.lim = bus, limits
        self.committed = 0
        self.halted = False
        bus.subscribe(SIGNAL_CREATED, self.on_signal)
        bus.subscribe(PNL_UPDATED, self.on_pnl)

    def _fail(self, ev: Event, rule: str, detail: str) -> None:
        self.bus.publish(RISK_FAILED, ev.ts, "risk", f"{rule}: {detail}", {"rule": rule}, parent=ev)

    def _pass(self, ev: Event, qty: int, reason: str) -> None:
        self.committed += qty
        self.bus.publish(RISK_PASSED, ev.ts, "risk", reason, {"qty": qty}, parent=ev)

    def on_signal(self, ev: Event) -> None:
        tgt = ev.payload["target"]
        qty = tgt - self.committed
        if self.halted:
            return self._fail(ev, "halted", "drawdown limit was breached earlier")
        if qty == 0:
            return self._fail(ev, "no_change", "already at target")
        if abs(tgt) > self.lim.position_limit:
            return self._fail(ev, "position_limit", f"|{tgt}| > {self.lim.position_limit}")
        if abs(qty) > self.lim.max_order:
            return self._fail(ev, "max_order", f"|{qty}| > {self.lim.max_order}")
        self._pass(ev, qty, f"move {self.committed} -> {tgt}")

    def on_pnl(self, ev: Event) -> None:
        if self.halted or ev.payload["drawdown"] <= self.lim.max_drawdown:
            return
        self.halted = True
        if self.committed != 0:
            self._pass(ev, -self.committed, f"drawdown {ev.payload['drawdown']:.2f} "
                                            f"> {self.lim.max_drawdown}: flatten and halt")


# ---------------------------------------------------------------- 5. execution simulation

class SimExchange:
    """Market orders only. Fills everything at the next tick, paying half the spread plus a fee."""

    def __init__(self, bus: EventBus, half_spread_bps: float = 2.0, fee_bps: float = 1.0) -> None:
        self.bus, self.hs, self.fee = bus, half_spread_bps / 1e4, fee_bps / 1e4
        self._pending: list[Event] = []
        bus.subscribe(RISK_PASSED, self.on_approved)
        bus.subscribe(MARKET_TICK, self.on_tick)

    def on_approved(self, ev: Event) -> None:
        sub = self.bus.publish(ORDER_SUBMITTED, ev.ts, "exchange", "market order queued for next tick",
                               {"qty": ev.payload["qty"]}, parent=ev)
        self._pending.append(sub)

    def on_tick(self, ev: Event) -> None:
        pending, self._pending = self._pending, []
        for sub in pending:
            qty, mid = sub.payload["qty"], ev.payload["price"]
            px = mid * (1 + self.hs) if qty > 0 else mid * (1 - self.hs)
            fee = abs(qty) * px * self.fee
            self.bus.publish(ORDER_FILLED, ev.ts, "exchange", "filled at next tick",
                             {"qty": qty, "price": px, "mid": mid, "fee": fee}, parent=sub)


# ---------------------------------------------------------------- 6. evaluation

class Portfolio:
    """Tracks cash, position and equity every tick; publishes PNL_UPDATED at every bar close."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.cash = 0.0
        self.position = 0
        self.fees = 0.0
        self.last = None
        self.peak = 0.0
        self.max_dd = 0.0
        self.equity_curve: list[float] = []
        bus.subscribe(ORDER_FILLED, self.on_fill)
        bus.subscribe(MARKET_TICK, self.on_tick)
        bus.subscribe(BAR_CLOSED, self.on_bar)

    @property
    def equity(self) -> float:
        return self.cash + self.position * (self.last or 0.0)

    def on_fill(self, ev: Event) -> None:
        p = ev.payload
        self.position += p["qty"]
        self.cash -= p["qty"] * p["price"] + p["fee"]
        self.fees += p["fee"]

    def on_tick(self, ev: Event) -> None:
        self.last = ev.payload["price"]
        eq = self.equity
        self.equity_curve.append(eq)
        self.peak = max(self.peak, eq)
        self.max_dd = max(self.max_dd, self.peak - eq)

    def on_bar(self, ev: Event) -> None:
        eq = self.equity
        self.bus.publish(PNL_UPDATED, ev.ts, "portfolio", "bar close mark-to-market",
                         {"equity": eq, "position": self.position,
                          "drawdown": self.peak - eq}, parent=ev)
