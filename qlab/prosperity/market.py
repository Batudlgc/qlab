"""Synthetic market generator: produces the order depths a Trader sees each tick.

Each product has a latent fair value and a book built around it by simulated
counterparties. The strategy never sees the fair value - only the book.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .datamodel import OrderDepth, Symbol


@dataclass
class ProductSpec:
    symbol: Symbol
    fair0: float = 10_000.0
    sigma: float = 1.2              # per-tick fair value volatility
    position_limit: int = 20
    base_half_spread: float = 2.0   # counterparty quoting width
    depth_levels: int = 3
    level_size: int = 15
    jump_prob: float = 0.0
    jump_size: float = 0.0
    mean_reversion: float = 0.0     # 0 = random walk, >0 pulls back to fair0
    bot_intensity: float = 0.6      # P(a bot market order arrives this tick)
    bot_size: int = 8               # max bot order size
    bot_informed: float = 0.35      # fraction of bot flow that knows fair value


class MarketGenerator:
    """Generates a fair-value path and a book around it for each product."""

    def __init__(self, specs: list[ProductSpec], n_ticks: int, seed: int = 0) -> None:
        self.specs = {s.symbol: s for s in specs}
        self.n_ticks = n_ticks
        self.rng = np.random.default_rng(seed)
        self.fair: dict[Symbol, np.ndarray] = {}
        for s in specs:
            self.fair[s.symbol] = self._path(s)

    def _path(self, s: ProductSpec) -> np.ndarray:
        steps = self.rng.normal(0, s.sigma, self.n_ticks)
        if s.jump_prob > 0:
            hits = self.rng.random(self.n_ticks) < s.jump_prob
            steps += hits * self.rng.choice([-1.0, 1.0], self.n_ticks) * s.jump_size
        path = np.empty(self.n_ticks)
        level = s.fair0
        for i, st in enumerate(steps):
            level += st + s.mean_reversion * (s.fair0 - level)
            path[i] = level
        return path

    def bot_flow(self, symbol: Symbol, t: int) -> list[tuple[int, int]]:
        """Market orders arriving this tick, as (side, size) with side +1 buy / -1 sell.

        A fraction `bot_informed` of the flow trades in the direction the fair
        value is about to move. That fraction is the source of adverse selection
        for anyone resting a quote.
        """
        s = self.specs[symbol]
        if self.rng.random() > s.bot_intensity:
            return []
        size = int(self.rng.integers(1, s.bot_size + 1))
        if self.rng.random() < s.bot_informed and t + 1 < self.n_ticks:
            drift = self.fair[symbol][t + 1] - self.fair[symbol][t]
            side = 1 if drift > 0 else -1
        else:
            side = 1 if self.rng.random() < 0.5 else -1
        return [(side, size)]

    def depth(self, symbol: Symbol, t: int) -> OrderDepth:
        s = self.specs[symbol]
        f = self.fair[symbol][t]
        hs = s.base_half_spread * (1 + 0.3 * self.rng.random())
        buys, sells = {}, {}
        for lvl in range(s.depth_levels):
            bid = int(round(f - hs - lvl))
            ask = int(round(f + hs + lvl))
            size = max(1, int(s.level_size * self.rng.uniform(0.4, 1.3) / (lvl + 1)))
            if bid < ask:
                buys[bid] = buys.get(bid, 0) + size
                sells[ask] = sells.get(ask, 0) - size
        return OrderDepth(buy_orders=buys, sell_orders=sells)
