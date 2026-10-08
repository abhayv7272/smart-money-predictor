#!/usr/bin/env python3
"""SWEEP TRACKER — pichle sweeps ka report card.
Daily sweeps: pichle 10 trading din | Weekly sweeps: pichle 3 closed weeks.
Har setup ka status: UPTREND / WATCH / FAILED + post-sweep chart.
Stateless: roz data se dobara compute hota hai (koi history file nahi chahiye).
"""
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep_engine import detect_all, SweepConfig
from weekly_sweep_engine import WeeklyParams
from index_screener import SKIP_PAT, slugify

DCFG = SweepConfig()
WCFG = WeeklyParams(min_weekly_bars=80)


def _status(close_now, sweep_close, level, sweep_low):
    if close_now < sweep_low:
        return "❌ FAIL (sweep low tod diya)"
    if close_now > sweep_close and close_now > level:
        return "✅ UPTREND chal raha"
    if close_now > level:
        return "🟡 WATCH (level ke upar tika hai)"
    return "🟠 KAMZOR (level ke niche, par sweep low nahi toda)"


def track_daily(master_path, days=10, chart_dir=None, max_charts=4):
    m = pd.read_csv(master_path, parse_dates=["Date"])
    latest = m["Date"].max()
    all_dates = sorted(m["Date"].unique())
    window = set(pd.Timestamp(d) for d in all_dates[-(days + 1):-1])  # aaj chhodke pichle N din
    tracked = {}
    for name, g in m.groupby("Index"):
        if SKIP_PAT.search(name):
            continue
        g = g.set_index("Date").sort_index()
        if len(g) < DCFG.min_bars + 5 or g.index[-1] != latest:
            continue
        sub = g[["Open", "High", "Low", "Close", "Volume"]]
        # sirf window ke bars par detect (tail slice se fast)
        tail = sub.tail(days + DCFG.min_bars + DCFG.level_lookback + 10)
        for r in detect_all(tail):
            d0 = pd.Timestamp(r["Date"])
            if d0 not in window:
                continue
            close_now = float(g["Close"].iloc[-1])
            days_ago = int((g.index > d0).sum())
            rec = dict(
                Index=name, Date=str(d0.date()), Days_Ago=days_ago,
                Sweep_Close=r["Close"], Level=r["Swept_Level"], Sweep_Low=r["Stop_Loss"],
                Close_Now=close_now, Ret_=100 * (close_now / r["Close"] - 1.0),
                Status=_status(close_now, r["Close"], r["Swept_Level"], r["Stop_Loss"]),
            )
            # ek index ka sabse recent sweep hi rakho
            if name not in tracked or tracked[name]["Days_Ago"] > days_ago:
                tracked[name] = rec
    rows = sorted(tracked.values(), key=lambda x: (x["Days_Ago"], -x["Ret_"]))
    charts = []
    if chart_dir and rows:
        os.makedirs(chart_dir, exist_ok=True)
        for rec in rows[:max_charts]:
            g = m[m["Index"] == rec["Index"]].set_index("Date").sort_index()
            p = os.path.join(chart_dir, f"track_{slugify(rec['Index'])}.png")
            _plot_track(g, rec, p, weekly=False)
            charts.append((rec["Index"], p))
    return rows, charts, latest


def track_weekly(master_path, weeks=3, chart_dir=None, max_charts=3, today=None):
    from weekly_sweep_engine import weekly_closed
    m = pd.read_csv(master_path, parse_dates=["Date"])
    tracked = {}
    wk_map = {}
    for name, g in m.groupby("Index"):
        if SKIP_PAT.search(name):
            continue
        g = g.set_index("Date").sort_index()
        if len(g) < 320:
            continue
        cols = ["Open", "High", "Low", "Close", "Volume"]
        wk = weekly_closed(g[cols], today=today)
        n = len(wk)
        if n < WCFG.min_weekly_bars:
            continue
        wk_map[name] = (g, wk)
        from weekly_sweep_engine import evaluate_bar
        for i in range(max(WCFG.min_weekly_bars, n - weeks), n):
            r = evaluate_bar(wk, i, WCFG)
            if r is None:
                continue
            close_now = float(g["Close"].iloc[-1])
            weeks_ago = n - 1 - i
            rec = dict(
                Index=name, Week=r["Date"], Weeks_Ago=weeks_ago,
                Sweep_Close=r["Close"], Level=r["Swept_Level"], Sweep_Low=r["Sweep_Low"],
                Pools=r["Pools_Taken"], Sweep_Type=r["Sweep_Type"],
                Close_Now=close_now, Ret_=100 * (close_now / r["Close"] - 1.0),
                Status=_status(close_now, r["Close"], r["Swept_Level"],
                               r["Sweep_Low"] * 0.995),
            )
            if name not in tracked or tracked[name]["Weeks_Ago"] > weeks_ago:
                tracked[name] = rec
    rows = sorted(tracked.values(), key=lambda x: (x["Weeks_Ago"], -x["Ret_"]))
    charts = []
    if chart_dir and rows:
        os.makedirs(chart_dir, exist_ok=True)
        for rec in rows[:max_charts]:
            g, wk = wk_map[rec["Index"]]
            p = os.path.join(chart_dir, f"wtrack_{slugify(rec['Index'])}.png")
            _plot_track(wk.reset_index().rename(columns={"index": "Date"}).set_index("Date"),
                        rec, p, weekly=True)
            charts.append((rec["Index"], p))
    return rows, charts


def _plot_track(g, rec, path, weekly=False, last_bars=None):
    last_bars = last_bars or (40 if weekly else 45)
    df = g.tail(last_bars)
    key = "Week" if weekly else "Date"
    sweep_ts = pd.Timestamp(rec[key])
    x = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(10, 5.2))
    sweep_pos = None
    for i, (ts, row) in enumerate(df.iterrows()):
        oo, hh, ll, cc = row["Open"], row["High"], row["Low"], row["Close"]
        col = "#1a7f37" if cc >= oo else "#c62828"
        ax.vlines(i, ll, hh, color=col, lw=1.0)
        ax.bar(i, max(abs(cc - oo), 1e-9), bottom=min(oo, cc), width=0.62,
               color=col, edgecolor=col, lw=0.5)
        if ts == sweep_ts:
            sweep_pos = i
    if sweep_pos is not None:
        ax.axvspan(sweep_pos - 0.45, len(df) - 0.5, color="#fff3e0", zorder=0)
        ax.annotate("SWEEP yahan hua \u2193", xy=(sweep_pos, df["High"].iloc[sweep_pos]),
                    xytext=(max(0, sweep_pos - 8), float(df["High"].max())),
                    fontsize=10, weight="bold", color="#e65100",
                    arrowprops=dict(arrowstyle="->", color="#e65100"))
    ax.axhline(rec["Level"], color="#e65100", ls="--", lw=1.4,
               label=f"swept level = {rec['Level']:.2f}")
    ax.axhline(rec["Sweep_Low"], color="#6a1b9a", ls=":", lw=1.2,
               label=f"fail niche = {rec['Sweep_Low']:.2f}")
    _map = {"\u2705": "WORKING", "\U0001F7E1": "WATCH", "\U0001F7E0": "KAMZOR", "\u274c": "FAILED"}
    status_short = _map.get(rec["Status"].split(" ")[0], "")
    ttl_unit = "hafte" if weekly else "din"
    ago = rec.get("Weeks_Ago", rec.get("Days_Ago", 0))
    ax.set_title(f"{rec['Index']} · sweep ke {ago} {ttl_unit} baad · "
                 f"{rec['Ret_']:+.1f}% since sweep · {status_short}",
                 fontsize=11, weight="bold")
    step = max(len(df) // 8, 1)
    ax.set_xticks(x[::step])
    fmt = "%d %b %y" if weekly else "%d %b"
    ax.set_xticklabels([d.strftime(fmt) for d in df.index[::step]], rotation=25, fontsize=8)
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close(fig)


def markdown_tracking(drows, dcharts, wrows, wcharts, chart_relpath="charts"):
    L = []
    L.append("## \U0001F4CB SWEEP REPORT CARD — pichle setups ab KAISE chal rahe hain?")
    L.append("")
    L.append("*Yahan har sweep 1-2 hafte tak dikhta rahega taaki khud dekh sako: "
             "sweep ke baad sach mein uptrend aaya ya nahi.*")
    L.append("")
    if drows:
        L.append(f"### \U0001F9F2 DAILY sweeps (pichle 10 din ke {len(drows)} setups):")
        L.append("")
        L.append("| Index | Sweep kab | Kitne din hue | Tab close | Ab close | Badlav | Status |")
        L.append("|-------|-----------|---------------|-----------|----------|--------|--------|")
        show_d = drows[:12]
        for r in show_d:
            L.append(f"| **{r['Index']}** | {r['Date']} | {r['Days_Ago']} din | "
                     f"{r['Sweep_Close']:.2f} | {r['Close_Now']:.2f} | "
                     f"**{r['Ret_']:+.1f}%** | {r['Status']} |")
        if len(drows) > 12:
            ok = sum(1 for r in drows[12:] if r["Status"].startswith("\u2705"))
            fail = sum(1 for r in drows[12:] if r["Status"].startswith("\u274c"))
            L.append(f"| *...aur {len(drows)-12} setups* | | | | | | "
                     f"*(unme \u2705 {ok} / \u274c {fail})* |")
        L.append("")
    else:
        L.append("### Pichle 10 din mein koi daily sweep nahi tha.")
        L.append("")
    if wrows:
        L.append(f"### \U0001F4C5 WEEKLY sweeps (pichle 3 closed weeks ke {len(wrows)} setups):")
        L.append("")
        L.append("| Index | Sweep week | Kitne hafte hue | Pools | Tab close | Ab close | Badlav | Status |")
        L.append("|-------|------------|-----------------|-------|-----------|----------|--------|--------|")
        show_w = wrows[:12]
        for r in show_w:
            pool_warn = " \u26a0\ufe0f" if r["Pools"] >= 2 else ""
            L.append(f"| **{r['Index']}** | {r['Week']} | {r['Weeks_Ago']} hafte | "
                     f"{r['Pools']}{pool_warn} | {r['Sweep_Close']:.2f} | {r['Close_Now']:.2f} | "
                     f"**{r['Ret_']:+.1f}%** | {r['Status']} |")
        if len(wrows) > 12:
            ok = sum(1 for r in wrows[12:] if r["Status"].startswith("\u2705"))
            fail = sum(1 for r in wrows[12:] if r["Status"].startswith("\u274c"))
            L.append(f"| *...aur {len(wrows)-12} setups* | | | | | | | "
                     f"*(unme \u2705 {ok} / \u274c {fail})* |")
        L.append("")
        w_ok = sum(1 for r in wrows if r["Status"].startswith("\u2705"))
        w_fail = sum(1 for r in wrows if r["Status"].startswith("\u274c"))
        L.append(f"**Scorecard (weekly):** \u2705 {w_ok} working | \u274c {w_fail} failed | "
                 f"baki watch/kamzor — market ke saath milake dekho (agar pura market gira hai "
                 f"to sweep-fail market ki galti hai, system ki nahi).")
        L.append("")
        L.append("\u26a0\ufe0f = Pools\u22652 (ek saath kai lows toda) — test mein ye setups KAMZOR nikle "
                 "(43% beat vs 59%), inse bachke raho.")
        L.append("")
    L.append("**Status samajhna:** ✅ = sweep sahi nikla, uptrend chal raha | "
             "🟡 = level ke upar hai, thoda aur time do | 🟠 = kamzor pada | "
             "❌ = sweep low toot gaya = setup FAIL, bhool jao")
    L.append("")
    for name, p in dcharts + wcharts:
        rel = f"{chart_relpath}/{os.path.basename(p)}"
        L.append(f"![{name}]({rel})")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    master = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "data/indices_ohlc_master.csv")
    cdir = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).resolve().parent.parent / "output/charts")
    drows, dcharts, latest = track_daily(master, chart_dir=cdir)
    wrows, wcharts = track_weekly(master, chart_dir=cdir)
    print(f"daily tracked: {len(drows)} | weekly tracked: {len(wrows)}")
    for r in drows:
        print(f"  D [{r['Days_Ago']:2d}d] {r['Index']:<42} {r['Ret_']:+.1f}%  {r['Status']}")
    for r in wrows:
        print(f"  W [{r['Weeks_Ago']}w] {r['Index']:<42} {r['Ret_']:+.1f}%  {r['Status']}")
    md = markdown_tracking(drows, dcharts, wrows, wcharts)
    open(Path(__file__).resolve().parent.parent / "output/latest_tracking.md", "w").write(md)
    print("markdown -> output/latest_tracking.md")
