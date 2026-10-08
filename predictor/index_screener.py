#!/usr/bin/env python3
"""INDEX SWEEP SCREENER — daily production module.
Input : long-format CSV (Date,Index,Open,High,Low,Close,Volume,TurnoverCr)
Output: list of sweep setups on the LATEST session + matplotlib charts + markdown section.
"""
import os
import sys
from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_engine import analyze_latest, SweepConfig

CFG = SweepConfig()

# Indices to ignore (not tradeable/meaningful for strength scan)
SKIP_PAT = re.compile(
    r"(dividend points|G-sec|Gsec|GS 10|GS 8|GS 4|GS 11|GS 15|Composite G-sec|"
    r"1D Rate|T-Bill|Tbill|SDL|Bharat Bond|CPSE Bond|Corporate Bond|Bond Index|"
    r"Arbitrage|Overnight|Liquid|Money Market|USD|Dollar|Total Return|TRI\b)", re.I)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_master(path):
    m = pd.read_csv(path, parse_dates=["Date"])
    return m


def rs_rank(m, lookback=20):
    """20d return percentile rank (0-100) for each index as of latest date."""
    px = m.pivot_table(index="Date", columns="Index", values="Close")
    if len(px) < lookback + 1:
        return {}
    r = px.iloc[-1] / px.iloc[-1 - lookback] - 1.0
    r = r.dropna()
    pct = r.rank(pct=True) * 100
    return {k: (float(pct[k]), float(100 * r[k])) for k in r.index}


def screen(master_path, chart_dir=None, top_charts=5):
    m = load_master(master_path)
    latest = m["Date"].max()
    ranks = rs_rank(m)
    setups = []
    for name, g in m.groupby("Index"):
        if SKIP_PAT.search(name):
            continue
        g = g.set_index("Date").sort_index()
        if len(g) < CFG.min_bars + 5:
            continue
        if g.index[-1] != latest:
            continue  # stale index
        rec = analyze_latest(g[["Open", "High", "Low", "Close", "Volume"]])
        if rec is None:
            continue
        rec["Index"] = name
        rs = ranks.get(name, (np.nan, np.nan))
        rec["RS_pct"] = rs[0]
        rec["Ret20d_"] = rs[1]
        # GRADE (1-yr validated, cross-sectional): sweep in ALREADY-STRONG index works best
        strong_rs = np.isfinite(rec["RS_pct"]) and rec["RS_pct"] >= 50
        if strong_rs and rec["E50"]:
            rec["Grade"] = "A+"      # trend + strong index: 10-20d best (+0.9% excess, 54-55% beat)
        elif strong_rs or rec["E50"]:
            rec["Grade"] = "B"
        else:
            rec["Grade"] = "C"       # counter-trend sweep in weak index: sirf info, no edge
        setups.append(rec)
    _g = {"A+": 0, "B": 1, "C": 2}
    setups.sort(key=lambda r: (_g[r["Grade"]],
                               -(r["RS_pct"] if np.isfinite(r["RS_pct"]) else 0.0)))
    charts = []
    if chart_dir and setups:
        os.makedirs(chart_dir, exist_ok=True)
        for r in setups[:top_charts]:
            g = m[m["Index"] == r["Index"]].set_index("Date").sort_index()
            p = os.path.join(chart_dir, f"sweep_{slugify(r['Index'])}.png")
            plot_setup(g, r, p)
            charts.append((r["Index"], p))
    return setups, charts, latest, ranks


def plot_setup(g, rec, path, last_bars=50):
    df = g.tail(last_bars)
    x = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for i, (oo, hh, ll, cc) in enumerate(zip(df["Open"], df["High"], df["Low"], df["Close"])):
        col = "#1a7f37" if cc >= oo else "#c62828"
        ax.vlines(i, ll, hh, color=col, lw=0.9)
        ax.bar(i, max(abs(cc - oo), 1e-9), bottom=min(oo, cc), width=0.62,
               color=col, edgecolor=col, lw=0.5)
    ax.axhline(rec["Swept_Level"], color="#e65100", ls="--", lw=1.5,
               label=f"swept level = {rec['Swept_Level']:.2f}")
    ax.axhline(rec["Stop_Loss"], color="#6a1b9a", ls=":", lw=1.2,
               label=f"sweep low / SL = {rec['Stop_Loss']:.2f}")
    ax.annotate("SWEEP \u2713", xy=(len(df) - 1, df["High"].iloc[-1]),
                xytext=(max(0, len(df) - 9), float(df["High"].max())),
                fontsize=11, weight="bold", color="#e65100")
    step = max(len(df) // 8, 1)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([d.strftime("%d %b") for d in df.index[::step]], rotation=25, fontsize=8)
    ax.set_title(f"{rec['Index']}  ·  liquidity sweep  ·  {df.index[-1].date()}  ·  "
                 f"score {rec['Score']:.0f}/100", fontsize=11, weight="bold")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close(fig)


def markdown_section(setups, charts, latest, ranks, chart_relpath="charts"):
    """Simple-Hinglish markdown section for the daily report."""
    L = []
    L.append("## \U0001F9F2 INDEX SWEEP SCANNER — konsa index STRONG hai?")
    L.append("")
    L.append(f"*Session: {pd.Timestamp(latest).date()} · scan: saare NSE indices (bond/G-sec chhodke)*")
    L.append("")
    L.append("**Ye kya hai (1 line):** Jab koi index apne purane LOW ke niche wick maar ke "
             "wapas UPAR band ho (= stop-loss hunt complete), to wo index aur uske stocks aage "
             "strong rehne ke candidate hain.")
    L.append("")
    if not setups:
        L.append("### Aaj koi sweep setup NAHI bana.")
        L.append("Koi baat nahi — ye roz nahi banta (mahine mein kuch hi baar aata hai). "
                 "Jis din banega, yahan chart ke saath dikhega.")
        return "\n".join(L)
    L.append(f"### \u2705 Aaj {len(setups)} index mein SWEEP COMPLETE hua:")
    L.append("")
    L.append("| # | GRADE | Index | 20d RS rank | Swept Level | Depth% | Wick% | Close vs Level | RSI | Trend(>E50) | Score |")
    L.append("|---|-------|-------|-------------|-------------|--------|-------|----------------|-----|-------------|-------|")
    for i, r in enumerate(setups, 1):
        rs = "" if not np.isfinite(r.get("RS_pct", np.nan)) else f"{r['RS_pct']:.0f}/100"
        gr = {"A+": "\U0001F7E2 A+", "B": "\U0001F7E1 B", "C": "\u26AA C"}[r["Grade"]]
        L.append(f"| {i} | {gr} | **{r['Index']}** | {rs} | {r['Swept_Level']:.2f} | "
                 f"{r['Sweep_Depth_']:.2f} | {r['LowerWick_']:.0f} | +{r['Above_Level_']:.2f}% | "
                 f"{r['RSI14']:.0f} | {'\u2705' if r['E50'] else '\u274c'} | {r['Score']:.0f} |")
    L.append("")
    L.append("**GRADE ka matlab (1 saal, 131 indices, 1,486 sweeps par test kiya):**")
    L.append("- \U0001F7E2 **A+** = sweep + index pehle se STRONG (RS\u226550) + trend upar \u2192 "
             "aage 10-20 din baaki market se behtar chalne ke best chances (+0.9% extra, 54-55% beat)")
    L.append("- \U0001F7E1 **B** = sweep + (strong RS *ya* uptrend, dono nahi) \u2192 theek-thaak, half conviction")
    L.append("- \u26AA **C** = weak index ka counter-trend sweep \u2192 KOI edge nahi mila, sirf jaankari")
    L.append("")
    best = setups[0]
    L.append(f"**Aaj ka #1: {best['Index']}** ({ {'A+':'\U0001F7E2 A+','B':'\U0001F7E1 B','C':'\u26AA C'}[best['Grade']] }) — "
             f"level {best['Swept_Level']:.2f} sweep karke +{best['Above_Level_']:.2f}% upar band hua.")
    L.append("")
    L.append("**Kaise use karna (swing ke liye):**")
    L.append("- Ye WATCHLIST hai, buy-order nahi — A+ wale index (aur uske bade stocks) nazar mein rakho")
    L.append(f"- Agle din index **{best['Swept_Level']:.2f} ke UPAR TIKA RAHE** to setup valid")
    L.append(f"- Setup FAIL = close wapas sweep low ({best['Stop_Loss']:.2f}) ke niche \u2192 bhool jao")
    L.append("- Paisa lagana hamesha MASTER SIGNAL (upar wala) ke hisab se — ye scanner sirf "
             "batata hai KONSA index/sector strong hai")
    L.append("")
    for name, p in charts:
        rel = f"{chart_relpath}/{os.path.basename(p)}"
        L.append(f"![{name}]({rel})")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    master = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "data/indices_ohlc_master.csv")
    cdir = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / "output/charts")
    setups, charts, latest, ranks = screen(master, chart_dir=cdir)
    print(f"latest session: {latest} | setups: {len(setups)}")
    for r in setups:
        print(f"  {r['Score']:5.1f}  {r['Index']:<40} level={r['Swept_Level']:.2f} "
              f"depth={r['Sweep_Depth_']:.2f}% wick={r['LowerWick_']:.0f}%")
    md = markdown_section(setups, charts, latest, ranks)
    open(Path(__file__).resolve().parent.parent / "output/latest_scan.md", "w").write(md)
    print("markdown -> output/latest_scan.md")
