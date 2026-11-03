"""Event-driven trading loop: market data -> strategy -> risk -> simulated execution -> PnL.

Simulated prices only. Nothing here connects to a broker.
"""
from .core import Event, EventBus
from .modules import DoNothing, MACross, RiskLimits
from .runner import RunResult, run, synthetic_ticks
