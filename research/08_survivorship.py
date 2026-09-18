"""Survivorship bias: how large is it, and can free data even measure it?

Experiment 1: how did removed index members behave before they were removed?
Experiment 2: the same momentum strategy on a survivor universe and on one that
              includes removed names, dropped at their removal date.

See reports/note_06_survivorship.md.

Run:  python3 research/08_survivorship.py
"""
import warnings, json; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

rem = pd.read_csv("qlab/universes/removed_with_data.csv", parse_dates=["removal_date"])
SURV = ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","AVGO","TSLA","JPM","V","UNH","XOM",
        "JNJ","PG","HD","COST","MRK","ABBV","PEP","KO","WMT","CVX","ADBE","CRM"]
tick = sorted(set(rem.ticker) | set(SURV) | {"SPY"})
px = yf.download(tick, start="2018-01-01", end="2026-08-01", progress=False,
                 auto_adjust=True, threads=True)["Close"]

# --- Experiment 1: how did removed names behave BEFORE removal? ---
rows=[]
for _,r in rem.iterrows():
    t=r.ticker
    if t not in px.columns: continue
    s=px[t].dropna(); b=px["SPY"].dropna()
    end=pd.Timestamp(r.removal_date)
    w=s.loc[:end]; wb=b.loc[:end]
    if len(w)<260: continue
    for horizon,label in [(252,"12m"),(126,"6m"),(63,"3m")]:
        if len(w)<horizon+1: continue
        rr=w.iloc[-1]/w.iloc[-horizon-1]-1
        rb=wb.iloc[-1]/wb.iloc[-horizon-1]-1
        rows.append({"ticker":t,"horizon":label,"stock":rr,"spy":rb,"excess":rr-rb})
d=pd.DataFrame(rows)
print("="*78); print("EXPERIMENT 1 - returns of removed names in the run-up to removal"); print("="*78)
g=d.groupby("horizon").agg(n=("excess","size"), mean_stock=("stock","mean"),
                            mean_spy=("spy","mean"), mean_excess=("excess","mean"),
                            median_excess=("excess","median"),
                            pct_underperf=("excess", lambda x:(x<0).mean()))
print(g.reindex(["3m","6m","12m"]).to_string(float_format=lambda x:f"{x:9.4f}"))
from scipy import stats
for h in ["3m","6m","12m"]:
    x=d[d.horizon==h]["excess"]
    t_,p_=stats.ttest_1samp(x,0)
    print(f"  {h}: mean excess {x.mean():+.4f}, t={t_:+.2f}, p={p_:.4f}, n={len(x)}")

# --- Experiment 2: momentum, survivors-only vs survivors+removed ---
import sys; sys.path.insert(0,'.')
from qlab import backtest, signals, validation
def bt(cols, dropout=None):
    p=px[cols].loc["2019-01-01":"2026-07-31"].ffill()
    p=p.dropna(axis=1, thresh=int(len(p)*0.5))
    sc=signals.momentum(p,lookback=126,skip=21)
    w=signals.to_weights(sc,top_n=5,gross=1.0)
    if dropout is not None:
        for t,dt in dropout.items():
            if t in w.columns: w.loc[w.index>pd.Timestamp(dt), t]=0.0
    days=w.groupby([w.index.year,w.index.month]).apply(lambda g:g.index[-1]).values
    w=w.where(pd.Series(w.index.isin(days),index=w.index),other=pd.NA).ffill().fillna(0.0).astype(float)
    return backtest.run(w, p.ffill(), costs=backtest.Costs())
surv=bt([c for c in SURV if c in px.columns])
allc=[c for c in set(SURV)|set(rem.ticker) if c in px.columns]
drop=dict(zip(rem.ticker, rem.removal_date))
full=bt(allc, dropout=drop)
print("\n"+"="*78); print("EXPERIMENT 2 - same strategy, two universes"); print("="*78)
res=pd.DataFrame({"survivors_only":surv.stats(),"survivors_plus_removed":full.stats()})
print(res.to_string(float_format=lambda x:f"{x:10.4f}"))
print(f"\nnames: survivors {len([c for c in SURV if c in px.columns])}, full {len(allc)}")
json.dump({"ok":1}, open("/tmp/surv_done.json","w"))
