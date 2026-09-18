"""Simulation loop: fair value process + agents + book, with PnL attribution."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .agents import InformedTrader, MarketMaker, NoiseTrader, Position
from .book import LimitOrderBook
from .types import Side


@dataclass
class Fees:
    """Exchange fee schedule, in currency units per unit traded.

    Most venues run maker-taker: the resting side is paid a rebate and the
    aggressing side pays a fee. A rebate can flip the sign on marginal fills,
    which is why a maker's break-even spread is not its quoted spread.
    """
    maker_rebate: float = 0.0
    taker_fee: float = 0.0


def fair_value_path(n_steps: int, rng, fair0: float = 100.0, sigma: float = 0.02,
                    jump_prob: float = 0.0, jump_size: float = 0.0) -> np.ndarray:
    """Fair value process: Gaussian diffusion with optional Poisson jumps.

    Jumps matter for testing quote staleness. Under pure diffusion a stale quote
    drifts out of the market and simply stops trading. A jump leaves it standing
    on the wrong side of a sudden move, which is when staleness actually costs.
    """
    steps = rng.normal(0, sigma, n_steps)
    if jump_prob > 0 and jump_size > 0:
        hits = rng.random(n_steps) < jump_prob
        signs = rng.choice([-1.0, 1.0], n_steps)
        steps = steps + hits * signs * jump_size
    return fair0 + np.cumsum(steps)


@dataclass
class SimResult:
    history: pd.DataFrame
    position: Position
    n_trades: int
    fills: pd.DataFrame = field(default_factory=pd.DataFrame)
    meta: dict = field(default_factory=dict)

    def markout(self, horizons: tuple[int, ...] = (1, 10, 50, 200)) -> dict:
        """Adverse selection, measured the way a trading desk measures it.

        For each fill, compare the traded price to the true fair value `k`
        steps later, signed by the direction the maker traded.

        Negative markout = the price moved against the maker after it traded
        = the maker was picked off. This isolates adverse selection from
        price discovery, spread capture, and inventory drift.
        """
        if self.fills.empty:
            return {}
        fair = self.history["fair"]
        out = {}
        for k in horizons:
            future = fair.reindex(self.fills["t"] + k).to_numpy()
            valid = ~pd.isna(future)
            pnl = (future[valid] - self.fills["price"].to_numpy()[valid]) * \
                  self.fills["signed_qty"].to_numpy()[valid]
            out[f"markout_{k}"] = float(pnl.sum())
            out[f"markout_{k}_per_unit"] = float(
                pnl.sum() / abs(self.fills["signed_qty"].to_numpy()[valid]).sum())
        return out

    def markout_by_counterparty(self, k: int = 200) -> pd.DataFrame:
        """Same markout, split by who the maker traded against."""
        if self.fills.empty:
            return pd.DataFrame()
        fair = self.history["fair"]
        f = self.fills.copy()
        f["future"] = fair.reindex(f["t"] + k).to_numpy()
        f = f.dropna(subset=["future"])
        f["markout"] = (f["future"] - f["price"]) * f["signed_qty"]
        g = f.groupby("counterparty").agg(
            fills=("markout", "size"),
            units=("qty", "sum"),
            markout_total=("markout", "sum"))
        g["markout_per_unit"] = g["markout_total"] / g["units"]
        return g

    def attribution(self) -> dict:
        """Decompose market-maker PnL.

        total = spread capture + inventory (position) PnL

        spread capture is what you earn for providing liquidity;
        inventory PnL is what the market does to you while you hold the risk.
        A market maker with positive total but hugely negative spread capture
        is not making markets, it is directionally punting.
        """
        h = self.history
        total = float(h["mtm"].iloc[-1])
        spread = float(self.position.spread_pnl)
        return {
            "total_pnl": total,
            "spread_capture": spread,
            "inventory_pnl": total - spread,
            "fills": self.position.fills,
            "final_inventory": self.position.inventory,
            "max_abs_inventory": int(h["inventory"].abs().max()),
            "pnl_per_fill": total / self.position.fills if self.position.fills else float("nan"),
            "inventory_vol": float(h["inventory"].std(ddof=1)),
        }


def simulate(n_steps: int = 5_000, seed: int = 0, fair0: float = 100.0,
             sigma: float = 0.02, mm: MarketMaker | None = None,
             informed_intensity: float = 0.3,
             noise_intensity: float = 0.5,
             ref_alpha: float = 0.05) -> SimResult:
    """Run a market-making simulation against noise and informed flow."""
    rng = np.random.default_rng(seed)
    book = LimitOrderBook(tick=0.01)
    mm = mm or MarketMaker()
    pos = Position(agent=mm.name)

    noise = NoiseTrader(intensity=noise_intensity,
                        rng=np.random.default_rng(seed + 100))
    informed = InformedTrader(intensity=informed_intensity,
                              rng=np.random.default_rng(seed + 200))

    fair = fair0
    mm_ref = fair0
    mm_fills: list[dict] = []          # the MM's OWN estimate of value - it never sees `fair`
    rows = []

    for t in range(n_steps):
        # fair value random walk. The informed trader observes it; the MM does not.
        fair += rng.normal(0, sigma)

        book.cancel_agent(mm.name)
        for o in mm.quotes(book, pos.inventory, fallback=mm_ref):
            book.submit(o)

        mid_before = book.mid
        for agent in (noise, informed):
            for o in agent.act(book, fair):
                for tr in book.submit(o):
                    if mm.name in (tr.buyer, tr.seller):
                        side = Side.BUY if tr.buyer == mm.name else Side.SELL
                        pos.on_fill(side, tr.price, tr.qty, mid_before)
                        mm_fills.append({"t": t, "price": tr.price, "qty": tr.qty,
                                         "signed_qty": tr.qty if side is Side.BUY else -tr.qty,
                                         "counterparty": tr.seller if side is Side.BUY else tr.buyer,
                                         "fair_at_fill": fair})
                    # the MM learns only from prints it can observe
                    mm_ref += ref_alpha * (tr.price - mm_ref)

        rows.append({
            "t": t, "fair": fair, "mm_ref": mm_ref, "mid": book.mid,
            "bid": book.best_bid, "ask": book.best_ask,
            "inventory": pos.inventory, "cash": pos.cash,
            "mtm": pos.mark_to_market(fair),
        })

    hist = pd.DataFrame(rows).set_index("t")
    fills_df = pd.DataFrame(mm_fills)
    return SimResult(history=hist, position=pos, n_trades=len(book.trades),
                     fills=fills_df,
                     meta={"seed": seed, "sigma": sigma,
                           "half_spread": mm.half_spread, "skew": mm.skew,
                           "informed_intensity": informed_intensity,
                           "ref_alpha": ref_alpha})


@dataclass
class MultiSimResult:
    history: pd.DataFrame
    positions: dict[str, Position]
    fills: pd.DataFrame
    queue: pd.DataFrame
    meta: dict = field(default_factory=dict)

    def summary(self, markout_k: int = 200) -> pd.DataFrame:
        fair = self.history["fair"]
        rows = []
        for name, pos in self.positions.items():
            f = self.fills[self.fills["maker"] == name].copy()
            row = {
                "maker": name,
                "total_pnl": pos.mark_to_market(float(fair.iloc[-1])),
                "spread_capture": pos.spread_pnl,
                "fills": pos.fills,
                "units": int(f["qty"].sum()) if not f.empty else 0,
                "final_inv": pos.inventory,
            }
            row["inventory_pnl"] = row["total_pnl"] - row["spread_capture"]
            if not f.empty:
                f["future"] = fair.reindex(f["t"] + markout_k).to_numpy()
                f = f.dropna(subset=["future"])
                if not f.empty:
                    mk = (f["future"] - f["price"]) * f["signed_qty"]
                    row["markout_per_unit"] = float(mk.sum() / f["qty"].sum())
                    inf = f[f["counterparty"] == "informed"]
                    if not inf.empty:
                        mk_i = (inf["future"] - inf["price"]) * inf["signed_qty"]
                        row["markout_vs_informed"] = float(mk_i.sum() / inf["qty"].sum())
                    row["pct_flow_informed"] = float(
                        inf["qty"].sum() / f["qty"].sum()) if not inf.empty else 0.0
            q = self.queue[self.queue["maker"] == name]
            row["avg_queue_ahead"] = float(q["ahead"].mean()) if not q.empty else float("nan")
            rows.append(row)
        return pd.DataFrame(rows).set_index("maker")


def simulate_multi(makers: list[MarketMaker], n_steps: int = 5_000, seed: int = 0,
                   fair0: float = 100.0, sigma: float = 0.02,
                   informed_intensity: float = 0.3, noise_intensity: float = 0.5,
                   ref_alpha: float = 0.05, jump_prob: float = 0.0,
                   jump_size: float = 0.0, fees: "Fees | None" = None) -> MultiSimResult:
    """Several makers competing for the same flow, with FIFO queue priority.

    Each maker keeps its own reference estimate and decides independently when
    to requote. A maker that cancels goes to the back of the queue at its price.
    """
    rng = np.random.default_rng(seed)
    fees = fees or Fees()
    path = fair_value_path(n_steps, rng, fair0, sigma, jump_prob, jump_size)
    book = LimitOrderBook(tick=0.01)
    names = [m.name for m in makers]
    if len(set(names)) != len(names):
        raise ValueError("makers must have unique names")

    pos = {m.name: Position(agent=m.name) for m in makers}
    refs = {m.name: fair0 for m in makers}
    live: dict[str, list[int]] = {m.name: [] for m in makers}
    # actions decided at step t but not yet visible to the book
    pending: dict[int, list[tuple]] = {}

    noise = NoiseTrader(intensity=noise_intensity, rng=np.random.default_rng(seed + 100))
    informed = InformedTrader(intensity=informed_intensity,
                              rng=np.random.default_rng(seed + 200))

    fair = fair0
    rows, fills, qsnap = [], [], []

    for t in range(n_steps):
        fair = float(path[t])

        # apply actions whose latency has elapsed
        for m_name, orders in pending.pop(t, []):
            book.cancel_agent(m_name)
            live[m_name] = []
            for o in orders:
                book.submit(o)
                live[m_name].append(o.id)

        # decide new quotes; they arrive at t + latency
        for m in rng.permutation(np.array(makers, dtype=object)):
            if not m.should_requote(t):
                continue
            orders = m.quotes(book, pos[m.name].inventory, fallback=refs[m.name])
            if m.latency <= 0:
                book.cancel_agent(m.name)
                live[m.name] = []
                for o in orders:
                    book.submit(o)
                    live[m.name].append(o.id)
            else:
                pending.setdefault(t + m.latency, []).append((m.name, orders))

        if t % 25 == 0:
            for name, ids in live.items():
                for oid in ids:
                    ahead = book.queue_ahead(oid)
                    if ahead is not None:
                        qsnap.append({"t": t, "maker": name, "ahead": ahead})

        mid_before = book.mid
        for agent in (noise, informed):
            for o in agent.act(book, fair):
                for tr in book.submit(o):
                    for name in names:
                        if name in (tr.buyer, tr.seller) and name != o.agent:
                            side = Side.BUY if tr.buyer == name else Side.SELL
                            pos[name].on_fill(side, tr.price, tr.qty, mid_before)
                            pos[name].cash += fees.maker_rebate * tr.qty
                            fills.append({
                                "t": t, "maker": name, "price": tr.price, "qty": tr.qty,
                                "signed_qty": tr.qty if side is Side.BUY else -tr.qty,
                                "counterparty": o.agent, "fair_at_fill": fair})
                    for name in names:
                        refs[name] += ref_alpha * (tr.price - refs[name])

        rows.append({"t": t, "fair": fair, "mid": book.mid,
                     "bid": book.best_bid, "ask": book.best_ask,
                     **{f"inv_{n}": pos[n].inventory for n in names}})

    return MultiSimResult(
        history=pd.DataFrame(rows).set_index("t"),
        positions=pos,
        fills=pd.DataFrame(fills),
        queue=pd.DataFrame(qsnap),
        meta={"seed": seed, "sigma": sigma, "informed_intensity": informed_intensity,
              "jump_prob": jump_prob, "jump_size": jump_size,
              "maker_rebate": fees.maker_rebate, "taker_fee": fees.taker_fee,
              "makers": {m.name: {"half_spread": m.half_spread, "skew": m.skew,
                                  "requote_every": m.requote_every,
                                  "latency": m.latency} for m in makers}})
