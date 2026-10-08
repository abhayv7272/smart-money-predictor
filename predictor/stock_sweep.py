#!/usr/bin/env python3
"""STOCK-LEVEL SWEEP SCREENER (Addition v18-E) — Nifty 50 stocks.
Tested rule (15y, IS<2020 / OOS>=2020, T+1 entry):
  A+ stock = Close > EMA50  AND  RS-rank >= 90th pctile (126-din return, peers ke beech)
  Excess vs equal-weight baseline: @20d +0.49/+0.30pp, @40d +1.03/+0.50pp, @60d +1.71/+1.12pp
  (dono periods positive — chhota par asli edge; horizon 1-3 mahine)
Rejected variants (test fail): simple >EMA50&RS>=50 (zero edge), mom12-1 top10/top5 (OOS weak).
Fail-safe: koi error to ("", []) return.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "nifty50_close.csv"


def _update_prices():
    """yfinance se latest closes append karo (Actions runner se chalega).
    Fail ho to chupchap purana data use karo."""
    try:
        df = pd.read_csv(DATA, parse_dates=["Date"]).set_index("Date")
    except Exception as e:
        print(f"[stocks] data load fail: {e}")
        return None
    try:
        import yfinance as yf
        tickers = list(df.columns)
        new = yf.download(tickers, period="10d", interval="1d",
                          auto_adjust=True, progress=False, threads=True)["Close"]
        if isinstance(new, pd.Series):
            new = new.to_frame()
        new = new.reindex(columns=df.columns)
        new.index = pd.to_datetime(new.index).tz_localize(None).normalize()
        add = new[~new.index.isin(df.index)].dropna(how="all")
        if len(add):
            df = pd.concat([df, add]).sort_index()
            df.to_csv(DATA)
            print(f"[stocks] +{len(add)} naye din (latest {df.index[-1].date()})")
    except Exception as e:
        print(f"[stocks] yfinance update fail ({e}) — purana data use")
    return df


def screen_stocks():
    """Returns (md_section, email_rows). email_rows = [(name, rs_pct, ret1m, price)]"""
    try:
        px = _update_prices()
        if px is None or len(px) < 200:
            return "", []
        px = px.ffill()
        ema50 = px.ewm(span=50).mean()
        rs_rank = px.pct_change(126).rank(axis=1, pct=True)
        ret21 = px.pct_change(21)

        last = px.index[-1]
        above = px.iloc[-1] > ema50.iloc[-1]
        rank = rs_rank.iloc[-1]
        r1m = ret21.iloc[-1] * 100

        aplus = rank[(rank >= 0.9) & above].sort_values(ascending=False)
        watch = rank[(rank >= 0.78) & (rank < 0.9) & above].sort_values(ascending=False).head(3)

        def nm(t):
            return t.replace(".NS", "").replace("-", "")

        rows, md_rows = [], []
        for t in aplus.index:
            rows.append((nm(t), int(rank[t] * 100), f"{r1m[t]:+.1f}%", f"{px.iloc[-1][t]:,.0f}"))
            md_rows.append(f"| **{nm(t)}** | A+ ⭐ | {int(rank[t]*100)} | {r1m[t]:+.1f}% | {px.iloc[-1][t]:,.0f} |")
        for t in watch.index:
            md_rows.append(f"| {nm(t)} | B (watch) | {int(rank[t]*100)} | {r1m[t]:+.1f}% | {px.iloc[-1][t]:,.0f} |")

        if not md_rows:
            md = f"""## 🏆 STOCK SWEEP — NIFTY 50 KE SABSE STRONG STOCKS ({last.date()})

Aaj koi A+ stock nahi (koi bhi top-10% RS + EMA50 ke upar nahi). Aisa kam hota hai —
market broad weak hai, stock-picking ka time nahi.
"""
            return md, []

        md = f"""## 🏆 STOCK SWEEP — NIFTY 50 KE SABSE STRONG STOCKS ({last.date()})

**Rule (15-saal tested):** A+ = price EMA50 ke upar **+** RS top-10% (126-din return, 50 stocks mein).
In stocks ne equal-weight basket ko average **+1.0pp (40 din) / +1.7pp (60 din)** se beat kiya
(out-of-sample bhi positive: +0.5/+1.1pp). Edge chhota par 15 saal consistent — horizon **1-3 mahine**.

| Stock | Grade | RS rank /100 | 1-mahina return | Price |
|---|---|---|---|---|
{chr(10).join(md_rows)}

> 💡 **Kaise use karein:** ye "kya kharidna" ka shortlist hai — lekin **kab/kitna** upar wala MASTER
> SIGNAL hi batayega. Entry signal weak ho to shortlist sirf watchlist hai. Stop-loss -10% yahan bhi pakka.
"""
        return md, rows
    except Exception as e:
        print(f"[stocks] skip: {e}")
        return "", []
