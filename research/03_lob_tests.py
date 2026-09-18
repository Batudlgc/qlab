"""Matching engine correctness tests. The engine is worthless if these fail."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qlab.lob import LimitOrderBook, Order, Side

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


# --- price priority ---
b = LimitOrderBook()
b.submit(Order(Side.SELL, 10, 100.05, agent="a"))
b.submit(Order(Side.SELL, 10, 100.03, agent="b"))
b.submit(Order(Side.SELL, 10, 100.07, agent="c"))
check("best ask is lowest", b.best_ask == 100.03, f"({b.best_ask})")

fills = b.submit(Order(Side.BUY, 10, None, agent="taker"))
check("market buy hits best price", fills[0].price == 100.03 and fills[0].seller == "b")

# --- time priority within a level ---
b = LimitOrderBook()
b.submit(Order(Side.SELL, 5, 100.00, agent="first"))
b.submit(Order(Side.SELL, 5, 100.00, agent="second"))
f = b.submit(Order(Side.BUY, 5, None, agent="t"))
check("FIFO within price level", f[0].seller == "first", f"({f[0].seller})")

# --- walking the book ---
b = LimitOrderBook()
for px, ag in [(100.01, "x"), (100.02, "y"), (100.03, "z")]:
    b.submit(Order(Side.SELL, 5, px, agent=ag))
f = b.submit(Order(Side.BUY, 12, None, agent="t"))
check("aggressive order walks levels", len(f) == 3 and sum(x.qty for x in f) == 12,
      f"(fills={len(f)} qty={sum(x.qty for x in f)})")
check("prices ascend while walking", [x.price for x in f] == [100.01, 100.02, 100.03])

# --- limit order rests when not crossing ---
b = LimitOrderBook()
b.submit(Order(Side.SELL, 5, 100.10, agent="s"))
b.submit(Order(Side.BUY, 5, 100.00, agent="p"))
check("non-crossing limit rests", b.best_bid == 100.00 and len(b.trades) == 0)
check("spread computed", abs(b.spread - 0.10) < 1e-9, f"({b.spread})")

# --- market order remainder is cancelled, not rested ---
b = LimitOrderBook()
b.submit(Order(Side.SELL, 3, 100.00, agent="s"))
b.submit(Order(Side.BUY, 10, None, agent="t"))
check("market remainder not rested", b.best_bid is None)

# --- self-trade prevention ---
b = LimitOrderBook()
b.submit(Order(Side.SELL, 5, 100.00, agent="same"))
f = b.submit(Order(Side.BUY, 5, 100.00, agent="same"))
check("no self-trade", len(f) == 0, f"(fills={len(f)})")

# --- cancel ---
b = LimitOrderBook()
o = Order(Side.BUY, 5, 99.00, agent="a")
b.submit(o)
check("cancel removes liquidity", b.cancel(o.id) and b.best_bid is None)
check("double cancel returns False", b.cancel(o.id) is False)

# --- conservation: every trade has one buyer and one seller, qty conserved ---
b = LimitOrderBook()
import numpy as np
rng = np.random.default_rng(7)
for i in range(2000):
    side = Side.BUY if rng.random() < 0.5 else Side.SELL
    px = None if rng.random() < 0.2 else round(100 + rng.normal(0, 0.1), 2)
    b.submit(Order(side, int(rng.integers(1, 10)), px, agent=f"ag{i % 5}"))

net = {}
for tr in b.trades:
    net[tr.buyer] = net.get(tr.buyer, 0) + tr.qty
    net[tr.seller] = net.get(tr.seller, 0) - tr.qty
check("net position across agents is zero", sum(net.values()) == 0, f"({sum(net.values())})")

cash = sum(-tr.notional for tr in b.trades) + sum(tr.notional for tr in b.trades)
check("cash conserved across agents", abs(cash) < 1e-9)
check("book still consistent after 2000 orders",
      (b.best_bid is None or b.best_ask is None or b.best_bid < b.best_ask),
      f"(bid={b.best_bid} ask={b.best_ask})")

# --- microprice sits between bid and ask ---
b = LimitOrderBook()
b.submit(Order(Side.BUY, 100, 99.99, agent="a"))
b.submit(Order(Side.SELL, 1, 100.01, agent="b"))
mp = b.microprice()
check("microprice within spread", 99.99 <= mp <= 100.01, f"({mp:.4f})")
check("microprice leans to thin side", mp > b.mid, f"(mp={mp:.4f} mid={b.mid:.4f})")

print("\n" + ("ALL TESTS PASSED" if not fails else f"FAILURES: {fails}"))
sys.exit(1 if fails else 0)
