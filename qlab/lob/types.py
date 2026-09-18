"""Core order book value types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import count


class Side(Enum):
    BUY = 1
    SELL = -1

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


_ids = count(1)


@dataclass
class Order:
    side: Side
    qty: int
    price: float | None = None      # None => market order
    agent: str = "anon"
    ts: int = 0
    id: int = field(default_factory=lambda: next(_ids))

    @property
    def is_market(self) -> bool:
        return self.price is None

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError("qty must be positive")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive")


@dataclass(frozen=True)
class Trade:
    price: float
    qty: int
    ts: int
    buyer: str
    seller: str
    aggressor: Side
    maker_order_id: int
    taker_order_id: int

    @property
    def notional(self) -> float:
        return self.price * self.qty
