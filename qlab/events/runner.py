"""Wire the modules to one bus and replay a price path through them."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .core import MARKET_TICK, ORDER_FILLED, RISK_FAILED, EventBus
from .modules import (MarketData, Portfolio, RiskLimits, RiskModule, SimExchange, Strategy,
                      StrategyModule)


def synthetic_ticks(n: int = 3000, seed: int = 0, p0: float = 100.0,
                    sigma: float = 0.001, drift: float = 0.0) -> np.ndarray:
    """Geometric random walk. Offline, seeded, so every replay is identical."""
    rng = np.random.default_rng(seed)
    return p0 * np.exp(np.cumsum(drift + sigma * rng.standard_normal(n)))


@dataclass
class RunResult:
    bus: EventBus
    portfolio: Portfolio
    risk: RiskModule

    def score(self) -> dict:
        pf = self.portfolio
        rejected: dict[str, int] = {}
        for e in self.bus.of_type(RISK_FAILED):
            rejected[e.payload["rule"]] = rejected.get(e.payload["rule"], 0) + 1
        return {
            "pnl": round(pf.equity, 4),
            "fees": round(pf.fees, 4),
            "fills": len(self.bus.of_type(ORDER_FILLED)),
            "final_position": pf.position,
            "max_drawdown": round(pf.max_dd, 4),
            "halted": self.risk.halted,
            "rejected": rejected,
            "events": self.bus.counts(),
        }


def run(prices, strategy: Strategy, limits: RiskLimits | None = None, bar_size: int = 10,
        half_spread_bps: float = 2.0, fee_bps: float = 1.0) -> RunResult:
    bus = EventBus()
    MarketData(bus, bar_size)
    StrategyModule(bus, strategy)
    risk = RiskModule(bus, limits or RiskLimits())
    SimExchange(bus, half_spread_bps, fee_bps)
    pf = Portfolio(bus)
    for t, p in enumerate(prices):
        bus.publish(MARKET_TICK, t, "replay", "recorded price", {"price": float(p)})
    return RunResult(bus, pf, risk)
