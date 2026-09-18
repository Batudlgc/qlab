"""Data model mirroring the IMC Prosperity trading interface.

UNOFFICIAL. This is a faithful reimplementation of the interface shape so that
strategies can be developed and tested locally between competition editions.
Field names and semantics follow the public Prosperity format, but this is not
IMC code and has not been validated against their engine. Re-check against the
official wiki when Prosperity 5 opens.

The contract a strategy implements:

    class Trader:
        def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
            ...
            return orders, conversions, trader_data

`trader_data` is a string round-tripped between timestamps - the only state a
strategy is allowed to carry, which is a real constraint worth practising under.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Symbol = str
Product = str
Position = int


@dataclass
class Listing:
    symbol: Symbol
    product: Product
    denomination: Product = "SEASHELLS"


@dataclass
class Order:
    symbol: Symbol
    price: int
    quantity: int          # positive = buy, negative = sell

    def __post_init__(self) -> None:
        if self.quantity == 0:
            raise ValueError("order quantity may not be zero")

    @property
    def is_buy(self) -> bool:
        return self.quantity > 0


@dataclass
class OrderDepth:
    """Aggregated resting volume by price.

    buy_orders  : price -> positive quantity available to sell into
    sell_orders : price -> negative quantity available to buy from
    """
    buy_orders: dict[int, int] = field(default_factory=dict)
    sell_orders: dict[int, int] = field(default_factory=dict)

    @property
    def best_bid(self) -> int | None:
        return max(self.buy_orders) if self.buy_orders else None

    @property
    def best_ask(self) -> int | None:
        return min(self.sell_orders) if self.sell_orders else None

    @property
    def mid(self) -> float | None:
        b, a = self.best_bid, self.best_ask
        return (b + a) / 2 if b is not None and a is not None else None

    @property
    def spread(self) -> int | None:
        b, a = self.best_bid, self.best_ask
        return a - b if b is not None and a is not None else None

    def microprice(self) -> float | None:
        b, a = self.best_bid, self.best_ask
        if b is None or a is None:
            return None
        qb, qa = self.buy_orders[b], abs(self.sell_orders[a])
        if qb + qa == 0:
            return (a + b) / 2
        return (a * qb + b * qa) / (qb + qa)


@dataclass
class Trade:
    symbol: Symbol
    price: int
    quantity: int
    buyer: str = ""
    seller: str = ""
    timestamp: int = 0


@dataclass
class Observation:
    plain_value_observations: dict[Product, int] = field(default_factory=dict)
    conversion_observations: dict[Product, dict] = field(default_factory=dict)


@dataclass
class TradingState:
    timestamp: int
    listings: dict[Symbol, Listing] = field(default_factory=dict)
    order_depths: dict[Symbol, OrderDepth] = field(default_factory=dict)
    own_trades: dict[Symbol, list[Trade]] = field(default_factory=dict)
    market_trades: dict[Symbol, list[Trade]] = field(default_factory=dict)
    position: dict[Product, Position] = field(default_factory=dict)
    observations: Observation = field(default_factory=Observation)
    traderData: str = ""
