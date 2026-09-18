"""Baseline strategies for the Prosperity harness.

These are references, not entries. Any real submission has to beat DoNothing on
risk-adjusted terms and beat MarketMaker on total PnL before it is interesting.
"""
from __future__ import annotations

import json

from .datamodel import Order, TradingState


class DoNothing:
    """The control. Any strategy that cannot beat zero has negative edge."""
    def run(self, state: TradingState):
        return {}, 0, ""


class MarketMaker:
    """Quotes inside the spread, leaning against inventory.

    `skew_ticks` is expressed relative to the position limit, so the maximum
    quote displacement is bounded by construction - the mistake documented in
    note 03, made impossible here rather than merely avoided.
    """

    def __init__(self, edge: int = 1, size: int = 8, max_skew_ticks: float = 1.0,
                 limits: dict[str, int] | None = None) -> None:
        self.edge = edge
        self.size = size
        self.max_skew_ticks = max_skew_ticks
        self.limits = limits or {}

    def run(self, state: TradingState):
        orders: dict[str, list[Order]] = {}
        for sym, book in state.order_depths.items():
            ref = book.microprice()
            if ref is None:
                continue
            pos = state.position.get(sym, 0)
            limit = self.limits.get(sym, 20)
            skew = self.max_skew_ticks * (pos / limit) if limit else 0.0
            centre = ref - skew

            bid = int(centre - self.edge)
            ask = int(centre + self.edge) + 1
            out = []
            buy_room = limit - pos
            sell_room = limit + pos
            if buy_room > 0:
                out.append(Order(sym, bid, min(self.size, buy_room)))
            if sell_room > 0:
                out.append(Order(sym, ask, -min(self.size, sell_room)))
            if out:
                orders[sym] = out
        return orders, 0, ""


class MeanReversion:
    """Fades deviations from a rolling mean carried in traderData.

    traderData is a string, so the rolling state has to be serialised each tick.
    That constraint is part of the exercise, not an inconvenience to work around.
    """

    def __init__(self, window: int = 40, entry_z: float = 1.5, size: int = 6,
                 limits: dict[str, int] | None = None) -> None:
        self.window = window
        self.entry_z = entry_z
        self.size = size
        self.limits = limits or {}

    def run(self, state: TradingState):
        try:
            hist = json.loads(state.traderData) if state.traderData else {}
        except json.JSONDecodeError:
            hist = {}

        orders: dict[str, list[Order]] = {}
        for sym, book in state.order_depths.items():
            mid = book.mid
            if mid is None:
                continue
            h = hist.setdefault(sym, [])
            h.append(round(mid, 2))
            if len(h) > self.window:
                del h[:-self.window]
            if len(h) < self.window:
                continue

            mean = sum(h) / len(h)
            var = sum((x - mean) ** 2 for x in h) / (len(h) - 1)
            sd = var ** 0.5
            if sd <= 1e-9:
                continue
            z = (mid - mean) / sd

            pos = state.position.get(sym, 0)
            limit = self.limits.get(sym, 20)
            if z > self.entry_z and book.best_bid is not None:
                qty = min(self.size, limit + pos)
                if qty > 0:
                    orders[sym] = [Order(sym, book.best_bid, -qty)]
            elif z < -self.entry_z and book.best_ask is not None:
                qty = min(self.size, limit - pos)
                if qty > 0:
                    orders[sym] = [Order(sym, book.best_ask, qty)]

        return orders, 0, json.dumps(hist, separators=(",", ":"))


class Combined:
    """Market-make the mean-reverting product, fade the trending one.

    Included to demonstrate per-product strategy dispatch, which is how
    Prosperity rounds are actually structured - different products behave
    differently and a single global rule is usually wrong.
    """

    def __init__(self, mm_symbols: set[str], mr_symbols: set[str],
                 limits: dict[str, int] | None = None) -> None:
        self.mm = MarketMaker(limits=limits)
        self.mr = MeanReversion(limits=limits)
        self.mm_symbols = mm_symbols
        self.mr_symbols = mr_symbols

    def run(self, state: TradingState):
        mm_state = _subset(state, self.mm_symbols)
        mr_state = _subset(state, self.mr_symbols)
        o1, _, _ = self.mm.run(mm_state)
        o2, _, td = self.mr.run(mr_state)
        return {**o1, **o2}, 0, td


def _subset(state: TradingState, symbols: set[str]) -> TradingState:
    return TradingState(
        timestamp=state.timestamp,
        listings={k: v for k, v in state.listings.items() if k in symbols},
        order_depths={k: v for k, v in state.order_depths.items() if k in symbols},
        own_trades={k: v for k, v in state.own_trades.items() if k in symbols},
        market_trades={k: v for k, v in state.market_trades.items() if k in symbols},
        position={k: v for k, v in state.position.items() if k in symbols},
        observations=state.observations,
        traderData=state.traderData,
    )
