"""Limit order book with price-time priority.

Matching rules implemented:
  - Best price first; within a price level, earliest arrival first (FIFO)
  - Incoming aggressive orders walk the book across levels
  - Unfilled remainder of a limit order rests; of a market order, is cancelled
  - A resting order is never matched against its own agent (self-trade prevention)
"""
from __future__ import annotations

from collections import deque
from sortedcontainers import SortedDict

from .types import Order, Side, Trade


class LimitOrderBook:
    def __init__(self, tick: float = 0.01) -> None:
        self.tick = tick
        # bids keyed by negative price so iteration order is best-first
        self._bids: SortedDict[float, deque[Order]] = SortedDict()
        self._asks: SortedDict[float, deque[Order]] = SortedDict()
        self._by_id: dict[int, Order] = {}
        self.trades: list[Trade] = []
        self.ts = 0

    # ---------- inspection ----------

    @property
    def best_bid(self) -> float | None:
        return -self._bids.peekitem(0)[0] if self._bids else None

    @property
    def best_ask(self) -> float | None:
        return self._asks.peekitem(0)[0] if self._asks else None

    @property
    def mid(self) -> float | None:
        b, a = self.best_bid, self.best_ask
        return (b + a) / 2 if b is not None and a is not None else None

    @property
    def spread(self) -> float | None:
        b, a = self.best_bid, self.best_ask
        return a - b if b is not None and a is not None else None

    def depth(self, side: Side, price: float) -> int:
        book = self._bids if side is Side.BUY else self._asks
        key = -price if side is Side.BUY else price
        return sum(o.qty for o in book.get(key, ()))

    def levels(self, side: Side, n: int = 5) -> list[tuple[float, int]]:
        book = self._bids if side is Side.BUY else self._asks
        out = []
        for key, q in list(book.items())[:n]:
            price = -key if side is Side.BUY else key
            out.append((price, sum(o.qty for o in q)))
        return out

    def queue_ahead(self, order_id: int) -> int | None:
        """Total resting quantity ahead of this order at its own price level.

        This is what determines fill probability. Two orders at the same price
        are not equivalent: the one behind 500 units of queue may never trade.
        """
        order = self._by_id.get(order_id)
        if order is None:
            return None
        book = self._bids if order.side is Side.BUY else self._asks
        key = -order.price if order.side is Side.BUY else order.price
        ahead = 0
        for o in book.get(key, ()):
            if o.id == order_id:
                return ahead
            ahead += o.qty
        return None

    def queue_rank(self, order_id: int) -> int | None:
        """Zero-based position in the FIFO queue at this order's price level."""
        order = self._by_id.get(order_id)
        if order is None:
            return None
        book = self._bids if order.side is Side.BUY else self._asks
        key = -order.price if order.side is Side.BUY else order.price
        for i, o in enumerate(book.get(key, ())):
            if o.id == order_id:
                return i
        return None

    def microprice(self) -> float | None:
        """Depth-weighted mid. Leans toward the side with less size resting."""
        b, a = self.best_bid, self.best_ask
        if b is None or a is None:
            return None
        qb, qa = self.depth(Side.BUY, b), self.depth(Side.SELL, a)
        if qb + qa == 0:
            return (a + b) / 2
        return (a * qb + b * qa) / (qb + qa)

    # ---------- mutation ----------

    def submit(self, order: Order) -> list[Trade]:
        """Submit an order; returns the trades it generated."""
        self.ts += 1
        order.ts = self.ts
        if order.price is not None:
            order.price = round(order.price / self.tick) * self.tick
        fills = self._match(order)
        if order.qty > 0 and not order.is_market:
            self._rest(order)
        return fills

    def cancel(self, order_id: int) -> bool:
        order = self._by_id.pop(order_id, None)
        if order is None:
            return False
        book = self._bids if order.side is Side.BUY else self._asks
        key = -order.price if order.side is Side.BUY else order.price
        q = book.get(key)
        if q is None:
            return False
        try:
            q.remove(order)
        except ValueError:
            return False
        if not q:
            del book[key]
        return True

    def cancel_agent(self, agent: str) -> int:
        ids = [oid for oid, o in self._by_id.items() if o.agent == agent]
        return sum(self.cancel(i) for i in ids)

    # ---------- internals ----------

    def _rest(self, order: Order) -> None:
        book = self._bids if order.side is Side.BUY else self._asks
        key = -order.price if order.side is Side.BUY else order.price
        book.setdefault(key, deque()).append(order)
        self._by_id[order.id] = order

    def _crosses(self, taker: Order, level_price: float) -> bool:
        if taker.is_market:
            return True
        return (taker.price >= level_price if taker.side is Side.BUY
                else taker.price <= level_price)

    def _match(self, taker: Order) -> list[Trade]:
        book = self._asks if taker.side is Side.BUY else self._bids
        fills: list[Trade] = []

        while taker.qty > 0 and book:
            key, queue = book.peekitem(0)
            level_price = key if taker.side is Side.BUY else -key
            if not self._crosses(taker, level_price):
                break

            skipped: deque[Order] = deque()
            traded_here = 0
            while queue and taker.qty > 0:
                maker = queue[0]
                if maker.agent == taker.agent:        # self-trade prevention
                    skipped.append(queue.popleft())
                    continue
                qty = min(taker.qty, maker.qty)
                maker.qty -= qty
                taker.qty -= qty
                traded_here += qty
                buyer = taker.agent if taker.side is Side.BUY else maker.agent
                seller = maker.agent if taker.side is Side.BUY else taker.agent
                fills.append(Trade(price=level_price, qty=qty, ts=self.ts,
                                   buyer=buyer, seller=seller,
                                   aggressor=taker.side,
                                   maker_order_id=maker.id,
                                   taker_order_id=taker.id))
                if maker.qty == 0:
                    queue.popleft()
                    self._by_id.pop(maker.id, None)

            while skipped:                            # restore skipped makers
                queue.appendleft(skipped.pop())
            if not queue:
                del book[key]
            elif traded_here == 0:
                # entire level is our own resting liquidity - no progress possible
                break

        self.trades.extend(fills)
        return fills

    def __repr__(self) -> str:
        b, a = self.best_bid, self.best_ask
        return (f"LOB(bid={b if b else '-'} ask={a if a else '-'} "
                f"spread={self.spread if self.spread else '-'} trades={len(self.trades)})")
