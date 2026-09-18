"""Limit order book simulation.

Built for market-making and execution research - the problem class that
IMC Prosperity and the Rotman RIT simulator actually test, which is
structurally different from cross-sectional alpha research.
"""
from .book import LimitOrderBook
from .types import Order, Side, Trade

__all__ = ["LimitOrderBook", "Order", "Side", "Trade"]
