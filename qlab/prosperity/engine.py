"""Runs a Trader against the synthetic market and scores it.

Rules enforced, matching the competition constraints that actually bite:
  - position limits per product, checked against the WORST CASE of all
    outstanding orders (an order that could breach the limit is rejected)
  - marketable orders fill immediately against resting depth
  - non-marketable orders REST for one tick and fill at the next tick if the
    market moves through them. This is what gives a maker fills at all, and it
    is also what makes those fills adversely selected: you are filled precisely
    when the market comes to you, which is when you were on the wrong side.
  - traderData is the only state carried between ticks
  - a strategy that raises is disqualified for that tick, not silently ignored
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .datamodel import Listing, Observation, Order, Trade, TradingState
from .market import MarketGenerator, ProductSpec


@dataclass
class RunResult:
    pnl: pd.DataFrame
    trades: pd.DataFrame
    rejected: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def score(self) -> dict:
        final = self.pnl.iloc[-1]
        total = float(final.filter(like="pnl_").sum())
        eq = self.pnl.filter(like="pnl_").sum(axis=1)
        rets = eq.diff().fillna(0.0)
        dd = eq - eq.cummax()
        return {
            "total_pnl": total,
            "sharpe_per_tick": float(rets.mean() / rets.std(ddof=1)) if rets.std(ddof=1) else float("nan"),
            "max_drawdown": float(dd.min()),
            "trades": len(self.trades),
            "volume": int(self.trades["quantity"].abs().sum()) if not self.trades.empty else 0,
            "rejected_orders": len(self.rejected),
            "errors": len(self.errors),
        }


def run_trader(trader, specs: list[ProductSpec], n_ticks: int = 2_000,
               seed: int = 0, verbose: bool = False) -> RunResult:
    gen = MarketGenerator(specs, n_ticks, seed=seed)
    symbols = [s.symbol for s in specs]
    limits = {s.symbol: s.position_limit for s in specs}

    position = {s: 0 for s in symbols}
    cash = {s: 0.0 for s in symbols}
    trader_data = ""
    own_trades = {s: [] for s in symbols}
    market_trades = {s: [] for s in symbols}

    rows, all_trades, rejected, errors = [], [], [], []
    resting: dict[str, list[Order]] = {s: [] for s in symbols}

    for t in range(n_ticks):
        depths = {s: gen.depth(s, t) for s in symbols}

        # (1) resting orders that the new book has moved through fill immediately
        # (2) bot market orders then sweep whatever resting quotes are best
        for sym in symbols:
            book = depths[sym]
            for o in resting[sym]:
                for px, qty in _try_fill(o, book, position, cash, sym, limits):
                    own_trades[sym].append(Trade(sym, px, qty, timestamp=t * 100))
                    all_trades.append({"t": t, "symbol": sym, "price": px,
                                       "quantity": qty, "kind": "passive_cross"})

            for side, size in gen.bot_flow(sym, t):
                remaining = size
                for o in resting[sym]:
                    if remaining <= 0:
                        break
                    # a bot buying lifts our resting sell, and vice versa
                    if side > 0 and o.quantity < 0:
                        best = book.best_ask
                        if best is not None and o.price > best:
                            continue          # our ask is worse than the book
                        qty = min(remaining, abs(o.quantity), limits[sym] + position[sym])
                        if qty <= 0:
                            continue
                        position[sym] -= qty
                        cash[sym] += qty * o.price
                        remaining -= qty
                        own_trades[sym].append(Trade(sym, o.price, -qty, timestamp=t * 100))
                        all_trades.append({"t": t, "symbol": sym, "price": o.price,
                                           "quantity": -qty, "kind": "passive_bot"})
                    elif side < 0 and o.quantity > 0:
                        best = book.best_bid
                        if best is not None and o.price < best:
                            continue          # our bid is worse than the book
                        qty = min(remaining, o.quantity, limits[sym] - position[sym])
                        if qty <= 0:
                            continue
                        position[sym] += qty
                        cash[sym] -= qty * o.price
                        remaining -= qty
                        own_trades[sym].append(Trade(sym, o.price, qty, timestamp=t * 100))
                        all_trades.append({"t": t, "symbol": sym, "price": o.price,
                                           "quantity": qty, "kind": "passive_bot"})
            resting[sym] = []
        state = TradingState(
            timestamp=t * 100,
            listings={s: Listing(s, s) for s in symbols},
            order_depths=depths,
            own_trades={s: list(own_trades[s]) for s in symbols},
            market_trades={s: list(market_trades[s]) for s in symbols},
            position=dict(position),
            observations=Observation(),
            traderData=trader_data,
        )

        try:
            orders, _conversions, trader_data = trader.run(state)
            trader_data = trader_data or ""
        except Exception as exc:                       # noqa: BLE001
            errors.append({"t": t, "error": f"{type(exc).__name__}: {exc}"})
            orders = {}

        own_trades = {s: [] for s in symbols}
        for sym, olist in (orders or {}).items():
            if sym not in symbols:
                rejected.append({"t": t, "symbol": sym, "reason": "unknown symbol"})
                continue
            book = depths[sym]
            # worst-case exposure check, the way a real limit works
            pending_buy = sum(o.quantity for o in olist if o.quantity > 0)
            pending_sell = -sum(o.quantity for o in olist if o.quantity < 0)
            if (position[sym] + pending_buy > limits[sym]
                    or position[sym] - pending_sell < -limits[sym]):
                rejected.append({"t": t, "symbol": sym, "reason": "position limit",
                                 "position": position[sym],
                                 "pending_buy": pending_buy, "pending_sell": pending_sell})
                continue

            for o in olist:
                filled = _try_fill(o, book, position, cash, sym, limits)
                got = sum(abs(q) for _, q in filled)
                for px, qty in filled:
                    tr = Trade(sym, px, qty, timestamp=t * 100)
                    own_trades[sym].append(tr)
                    all_trades.append({"t": t, "symbol": sym, "price": px,
                                       "quantity": qty, "kind": "aggressive"})
                left = abs(o.quantity) - got
                if left > 0:
                    resting[sym].append(
                        Order(sym, o.price, left if o.is_buy else -left))

        row = {"t": t}
        for s in symbols:
            mid = depths[s].mid if depths[s].mid is not None else gen.fair[s][t]
            row[f"pos_{s}"] = position[s]
            row[f"pnl_{s}"] = cash[s] + position[s] * mid
            row[f"mid_{s}"] = mid
        rows.append(row)

    return RunResult(pnl=pd.DataFrame(rows).set_index("t"),
                     trades=pd.DataFrame(all_trades),
                     rejected=rejected, errors=errors)


def _try_fill(o: Order, book, position, cash, sym, limits) -> list[tuple[int, int]]:
    """Fill an order against resting depth at or better than its price."""
    fills = []
    remaining = abs(o.quantity)
    if o.is_buy:
        levels = sorted(p for p in book.sell_orders if p <= o.price)
        for px in levels:
            avail = abs(book.sell_orders[px])
            if avail <= 0 or remaining <= 0:
                continue
            room = limits[sym] - position[sym]
            qty = min(remaining, avail, max(0, room))
            if qty <= 0:
                break
            book.sell_orders[px] += qty
            position[sym] += qty
            cash[sym] -= qty * px
            remaining -= qty
            fills.append((px, qty))
    else:
        levels = sorted((p for p in book.buy_orders if p >= o.price), reverse=True)
        for px in levels:
            avail = book.buy_orders[px]
            if avail <= 0 or remaining <= 0:
                continue
            room = limits[sym] + position[sym]
            qty = min(remaining, avail, max(0, room))
            if qty <= 0:
                break
            book.buy_orders[px] -= qty
            position[sym] -= qty
            cash[sym] += qty * px
            remaining -= qty
            fills.append((px, -qty))
    return fills
