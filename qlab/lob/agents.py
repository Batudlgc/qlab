"""Simulation agents.

The point of the cast: a market maker earns the spread from uninformed flow
and loses to informed flow. If your simulator has no informed traders, your
market maker will look profitable for the wrong reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .book import LimitOrderBook
from .types import Order, Side


@dataclass
class Position:
    agent: str
    inventory: int = 0
    cash: float = 0.0
    spread_pnl: float = 0.0     # earned vs mid at time of fill
    fills: int = 0

    def on_fill(self, side: Side, price: float, qty: int, mid: float | None) -> None:
        signed = qty if side is Side.BUY else -qty
        self.inventory += signed
        self.cash -= signed * price
        if mid is not None:
            # positive when you bought below mid or sold above it
            self.spread_pnl += (mid - price) * signed
        self.fills += 1

    def mark_to_market(self, mid: float | None) -> float:
        if mid is None:
            return self.cash
        return self.cash + self.inventory * mid


@dataclass
class NoiseTrader:
    """Uninformed flow. Trades at random, indifferent to value."""
    name: str = "noise"
    intensity: float = 0.5
    size: int = 5
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(0))

    def act(self, book: LimitOrderBook, fair: float) -> list[Order]:
        if self.rng.random() > self.intensity:
            return []
        side = Side.BUY if self.rng.random() < 0.5 else Side.SELL
        qty = int(self.rng.integers(1, self.size + 1))
        return [Order(side=side, qty=qty, price=None, agent=self.name)]


@dataclass
class InformedTrader:
    """Knows the fair value. Only lifts quotes that are mispriced.

    This agent is the source of adverse selection - the market maker's real cost.
    """
    name: str = "informed"
    edge: float = 0.02          # only trades when mispricing exceeds this
    size: int = 5
    intensity: float = 0.3
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(1))

    def act(self, book: LimitOrderBook, fair: float) -> list[Order]:
        if self.rng.random() > self.intensity:
            return []
        bid, ask = book.best_bid, book.best_ask
        qty = int(self.rng.integers(1, self.size + 1))
        if ask is not None and fair - ask > self.edge:
            return [Order(side=Side.BUY, qty=qty, price=ask, agent=self.name)]
        if bid is not None and bid - fair > self.edge:
            return [Order(side=Side.SELL, qty=qty, price=bid, agent=self.name)]
        return []


@dataclass
class MarketMaker:
    """Quotes both sides, skewing to mean-revert inventory.

    half_spread : base distance from reference price
    skew        : how hard to lean quotes against existing inventory
    max_inv     : stop quoting the side that would worsen inventory beyond this
    """
    name: str = "mm"
    half_spread: float = 0.05
    skew: float = 0.01
    size: int = 10
    max_inv: int = 50
    use_microprice: bool = True
    requote_every: int = 1
    """How often the maker refreshes its quotes.

    Cancelling and resubmitting sends you to the back of the FIFO queue.
    Requoting every step keeps your price current but destroys queue priority;
    requoting rarely preserves priority but leaves stale quotes exposed.
    This parameter is that trade-off.
    """

    latency: int = 0
    """Steps between deciding to quote (or cancel) and the book acting on it.

    The expensive half is the cancel. A maker that sees the market move and
    pulls its quote still leaves that quote resting for `latency` steps, during
    which anyone with a faster path can take it. Latency is not a delay in
    getting filled; it is a window in which you cannot stop being filled.
    """

    def should_requote(self, t: int) -> bool:
        return t % self.requote_every == 0

    def quotes(self, book: LimitOrderBook, inventory: int,
               fallback: float) -> list[Order]:
        ref = (book.microprice() if self.use_microprice else book.mid) or fallback
        adj = ref - self.skew * inventory      # long inventory -> quote lower
        orders = []
        if inventory < self.max_inv:
            orders.append(Order(side=Side.BUY, qty=self.size,
                                price=adj - self.half_spread, agent=self.name))
        if inventory > -self.max_inv:
            orders.append(Order(side=Side.SELL, qty=self.size,
                                price=adj + self.half_spread, agent=self.name))
        return orders
