#!/usr/bin/env python3
"""WEEKLY INDEX SWEEP SCREENER — production module.
Scans all NSE indices for a completed weekly liquidity sweep on the last CLOSED week.
Outputs setups + weekly-candle charts + simple-Hinglish markdown section.
"""
import os
import re
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weekly_sweep_engine import analyze_latest_weekly, analyze_forming_weekly, WeeklyParams

P = WeeklyParams(min_weekly_bars=80)

SKIP_PAT = re.compile(
    r"(dividend points|G-sec|Gsec|GS 10|GS 8|GS 4|GS 11|GS 15|Composite G-sec|"
    r"1D Rate|T-Bill|Tbill|SDL|Bharat Bond|CPSE Bond|Corporate Bond|Bond Index|"
    r"Arbitrage|Overnight|Liquid|Money Market|USD|Dollar|Total Return|TRI\b)", re.I)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def weekly_rs_rank(m, lookback_w=8):
    """8-week return percentile rank per index (weekly RS)."""
    px = m.pivot_table(index="Date", columns="Index", values="Close")
    wk = px.resample("W-FRI").last().dropna(how="all")
    if len(wk) < lookback_w + 1:
        return {}
    r = (wk.iloc[-1] / wk.iloc[-1 - lookback_w] - 1.0).dropna()
    pct = r.rank(pct=True) * 100
    return {k: (float(pct[k]), float(100 * r[k])) for k in r.index}


def screen_weekly(master_path, chart_dir=None, top_charts=5, today=None):
    m = pd.read_csv(master_path, parse_dates=["Date"])
    ranks = weekly_rs_rank(m)
    setups = []
    forming = []
    latest = m["Date"].max()
    for name, g in m.groupby("Index"):
        if SKIP_PAT.search(name):
            continue
        g = g.set_index("Date").sort_index()
        cols = ["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in g.columns else [])
        # current running week mein sweep ban raha hai? (sirf info)
        frec, _ = analyze_forming_weekly(g[cols], P, today=today)
        if frec is not None:
            frec["Index"] = name
            rsf = ranks.get(name, (np.nan, np.nan))
            frec["RS_pct"] = rsf[0]
            forming.append(frec)
        rec, wk = analyze_latest_weekly(g[cols], P, today=today)
        if rec is None:
            continue
        rec["Index"] = name
        rs = ranks.get(name, (np.nan, np.nan))
        rec["RS_pct"] = rs[0]
        # WEEKLY grading (2yr cross-sectional, 303 events): RS>=50 hi asli qualifier hai
        # (RS>=50: +8w +2.46% excess, 69% beat | baaki: ~+0.45%, ~50% = no edge)
        # NOTE: trend filter weekly par kaam NAHI karta (tested) — grade mein use nahi hota
        strong_rs = np.isfinite(rec["RS_pct"]) and rec["RS_pct"] >= 50
        rec["Grade"] = "A+" if strong_rs else "B"
        rec["_wk"] = wk
        setups.append(rec)
    _g = {"A+": 0, "B": 1}
    setups.sort(key=lambda r: (_g[r["Grade"]],
                               -(r["RS_pct"] if np.isfinite(r["RS_pct"]) else 0.0)))
    charts = []
    if chart_dir and setups:
        os.makedirs(chart_dir, exist_ok=True)
        for r in setups[:top_charts]:
            p = os.path.join(chart_dir, f"wsweep_{slugify(r['Index'])}.png")
            plot_weekly_setup(r["_wk"], r, p)
            charts.append((r["Index"], p))
    for r in setups:
        r.pop("_wk", None)
    forming.sort(key=lambda r: -(r["RS_pct"] if np.isfinite(r["RS_pct"]) else 0.0))
    return setups, charts, latest, forming


def plot_weekly_setup(wk, rec, path, last_bars=60):
    df = wk.tail(last_bars)
    x = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for i, (oo, hh, ll, cc) in enumerate(zip(df["Open"], df["High"], df["Low"], df["Close"])):
        col = "#1a7f37" if cc >= oo else "#c62828"
        ax.vlines(i, ll, hh, color=col, lw=1.0)
        ax.bar(i, max(abs(cc - oo), 1e-9), bottom=min(oo, cc), width=0.62,
               color=col, edgecolor=col, lw=0.5)
    ax.axhline(rec["Swept_Level"], color="#e65100", ls="--", lw=1.5,
               label=f"swept weekly level = {rec['Swept_Level']:.2f}")
    ax.axhline(rec["Stop"], color="#6a1b9a", ls=":", lw=1.2,
               label=f"stop = {rec['Stop']:.2f}")
    ax.annotate("WEEKLY SWEEP \u2713", xy=(len(df) - 1, df["High"].iloc[-1]),
                xytext=(max(0, len(df) - 14), float(df["High"].max())),
                fontsize=11, weight="bold", color="#e65100")
    step = max(len(df) // 8, 1)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([d.strftime("%d %b %y") for d in df.index[::step]], rotation=25, fontsize=8)
    ax.set_title(f"{rec['Index']}  ·  WEEKLY liquidity sweep ({rec['Sweep_Type']})  ·  "
                 f"week of {rec['Date']}  ·  score {rec['Score']:.0f}", fontsize=11, weight="bold")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close(fig)


def markdown_section_weekly(setups, charts, latest, chart_relpath="charts", forming=None):
    L = []
    L.append("## \U0001F4C5 WEEKLY SWEEP SCANNER — bada timeframe, zyada strong signal")
    L.append("")
    L.append(f"*Last closed week ke hisab se · data till {pd.Timestamp(latest).date()} · "
             "ye signal pura hafta valid rehta hai*")
    L.append("")
    L.append("**Ye kya hai (1 line):** Jo kaam daily sweep 1 din mein karta hai, wahi WEEKLY candle "
             "par ho to bade khiladi ka POORE HAFTE ka sauda dikhta hai — isliye ye signal zyada "
             "bharosemand hai (15-saal test: Nifty +8 hafte 69% win, Bank Nifty 76% win).")
    L.append("")
    if not setups:
        L.append("### Pichle closed week mein koi WEEKLY sweep setup NAHI bana.")
        L.append("Ye normal hai — weekly sweep rare hota hai. Jis hafte aayega, yahan chart ke saath dikhega.")
        L.append("")
        _append_forming(L, forming)
        return "\n".join(L)
    L.append(f"### \u2705 Pichle closed week mein {len(setups)} index par WEEKLY SWEEP COMPLETE:")
    L.append("")
    L.append("| # | GRADE | Index | Sweep type | Swept Level | Depth% | Wick% | Pools | 8w RS | Trend | Score |")
    L.append("|---|-------|-------|-----------|-------------|--------|-------|-------|-------|-------|-------|")
    for i, r in enumerate(setups, 1):
        rs = "" if not np.isfinite(r.get("RS_pct", np.nan)) else f"{r['RS_pct']:.0f}/100"
        gr = {"A+": "\U0001F7E2 A+", "B": "\U0001F7E1 B"}[r["Grade"]]
        L.append(f"| {i} | {gr} | **{r['Index']}** | {r['Sweep_Type']} | {r['Swept_Level']:.2f} | "
                 f"{r['Depth_']:.2f} | {r['Wick_']:.0f} | {r['Pools_Taken']} | {rs} | "
                 f"{'\u2705' if r['Trend'] else '\u274c'} | {r['Score']:.0f} |")
    L.append("")
    L.append("**GRADE ka matlab (2 saal, 106 indices, 303 weekly sweeps par test):**")
    L.append("- \U0001F7E2 **A+** = sweep + index pehle se STRONG (8-hafte RS\u226550) \u2192 "
             "agle 8 hafte market se +2.5% extra, 69% baar beat — YE wale par dhyan do")
    L.append("- \U0001F7E1 **B** = sweep hua par index kamzor tha \u2192 edge nahi mila, sirf jaankari")
    L.append("")
    best = setups[0]
    L.append(f"**Is hafte ka #1: {best['Index']}** — {best['Sweep_Type']}, level "
             f"{best['Swept_Level']:.2f} raid karke +{best['Above_']:.2f}% upar band hua "
             f"({best['Pools_Taken']} liquidity pool ek saath saaf kiye).")
    L.append("")
    L.append("**Kaise use karna (15-saal validated, swing 4-8 hafte):**")
    L.append("- Weekly sweep = zyada strong — ye index/sector agle 1-2 MAHINE outperform karne ka candidate")
    L.append(f"- Invalidation: weekly close wapas {best['Stop']:.2f} (sweep low) ke niche = setup fail")
    L.append("- Nifty/BankNifty par 15-saal test: sweep ke baad +8 hafte mein 69-76% baar upar, "
             "baseline se ~1-1.4% zyada")
    L.append("- Daily scanner (upar) = roz ka nazara; WEEKLY scanner = bada aur pakka footprint. "
             "Dono ek hi index par aayein = SABSE strong combo")
    L.append("- Paisa kitna lagana hai: hamesha MASTER SIGNAL ke deploy % se")
    L.append("")
    for name, pth in charts:
        rel = f"{chart_relpath}/{os.path.basename(pth)}"
        L.append(f"![{name}]({rel})")
        L.append("")
    _append_forming(L, forming)
    return "\n".join(L)


def _append_forming(L, forming):
    if not forming:
        return
    L.append("### \u23F3 IS HAFTE BAN RAHE HAIN (abhi confirm NAHI — Friday close ka wait karo):")
    L.append("")
    L.append("| Index | Sweep type | Level | 8w RS | Score (abhi tak) |")
    L.append("|-------|-----------|-------|-------|------------------|")
    for r in forming[:10]:
        rs = "" if not np.isfinite(r.get("RS_pct", np.nan)) else f"{r['RS_pct']:.0f}/100"
        L.append(f"| {r['Index']} | {r['Sweep_Type']} | {r['Swept_Level']:.2f} | {rs} | {r['Score']:.0f} |")
    L.append("")
    L.append("\u26A0\ufe0f Hafta khatam hone se pehle ye badal/gayab ho sakte hain — "
             "sirf nazar rakho, act Friday ke baad.")
    L.append("")


if __name__ == "__main__":
    master = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "data/indices_ohlc_master.csv")
    cdir = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / "output/charts")
    setups, charts, latest, forming = screen_weekly(master, chart_dir=cdir)
    print(f"data till: {latest} | weekly setups: {len(setups)}")
    for r in setups:
        print(f"  [{r['Grade']:2s}] {r['Score']:5.1f}  {r['Index']:<42} {r['Sweep_Type']:<22} "
              f"level={r['Swept_Level']:.2f} wick={r['Wick_']:.0f}%")
    md = markdown_section_weekly(setups, charts, latest, forming=forming)
    open(Path(__file__).resolve().parent.parent / "output/latest_weekly_scan.md", "w").write(md)
    print("markdown -> output/latest_weekly_scan.md")
