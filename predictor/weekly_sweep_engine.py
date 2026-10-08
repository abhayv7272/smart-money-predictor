#!/usr/bin/env python3
"""
WEEKLY LIQUIDITY SWEEP ENGINE — index edition.
Faithful port of the user's Colab 'NSE Weekly Liquidity-Sweep Screener' (stocks),
adapted for indices (volume optional). Core rule (all hard gates):
  1. weekly sweep of a swing low on the last CLOSED weekly candle
  2. swept low may be OLD (confirmed fractal) or NEW (window low / 52w low)
  3. close back ABOVE the level (min_close_above_pct)
  4. proper rejection wick (wick ratio + wick-vs-body + close in upper range)
Depth capped by % and by ATR(14w). Deepest pool taken is reported.
Score 0-100: wick 22, close_pos 16, depth 12, volume 10, trend 12,
proximity 10, structure 10, recency 8 (volume redistributed when absent).
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

EPS = 1e-12


@dataclass
class WeeklyParams:
    min_weekly_bars: int = 80          # original 104; indices ke paas ~104 hi hai (2yr)
    swing_strength: int = 2
    swing_lookback: int = 26
    min_swing_age: int = 2
    allow_fresh_low: bool = True
    max_sweep_bars_ago: int = 1
    min_close_above_pct: float = 0.002
    min_wick_ratio: float = 0.34
    min_wick_body_mult: float = 1.15
    min_close_in_range: float = 0.50
    min_depth_pct: float = 0.002
    max_depth_pct: float = 0.16
    max_depth_atr_mult: float = 3.0
    max_range_of_close: float = 0.12
    require_green_close: bool = False
    weights: dict = field(default_factory=lambda: {
        "wick": 22.0, "close_position": 16.0, "depth": 12.0, "volume": 10.0,
        "trend": 12.0, "proximity": 10.0, "structure": 10.0, "recency": 8.0,
    })


P = WeeklyParams()


def _ramp(x, lo, hi):
    if x is None or not np.isfinite(x):
        return 0.0
    return float(np.clip((x - lo) / max(hi - lo, EPS), 0.0, 1.0))


def _band(x, a, b, c, d):
    if x is None or not np.isfinite(x):
        return 0.0
    if x <= a:
        return 0.0
    if x < b:
        return float((x - a) / max(b - a, EPS))
    if x <= c:
        return 1.0
    if x >= d:
        return 0.0
    return float((d - x) / max(d - c, EPS))


def to_weekly(df):
    """Daily OHLC(V) -> weekly (Mon-Fri, stamped with the FRIDAY/last session of the week)."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    if "Volume" in df.columns:
        agg["Volume"] = "sum"
    wk = df.resample("W-FRI").agg(agg).dropna(subset=["Open", "High", "Low", "Close"])
    return wk


def weekly_closed(df, today=None):
    """Weekly bars, dropping the currently-running (not yet closed) week."""
    wk = to_weekly(df)
    if len(wk) == 0:
        return wk
    last_daily = df.index.max()
    # week is closed if the last daily bar is a Friday OR the week-end stamp < today
    wk_end = wk.index[-1]
    if last_daily.weekday() != 4 and (today is None or pd.Timestamp(today) <= wk_end):
        wk = wk.iloc[:-1]
    return wk


def _atr(wk, i, n=14):
    h = wk["High"].to_numpy(float)[max(0, i - n):i]
    l = wk["Low"].to_numpy(float)[max(0, i - n):i]
    c = wk["Close"].to_numpy(float)[max(0, i - n - 1):i]
    if len(h) < 4:
        return np.nan
    pc = c[:-1] if len(c) > len(h) else np.concatenate([[c[0]], c[:-1]])[:len(h)]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc[:len(h)]), np.abs(l - pc[:len(h)])))
    return float(np.nanmean(tr))


def _confirmed_swings(low, i, p):
    """Confirmed fractal swing lows j (low[j] strict-ish min of ±k) usable at bar i:
    j+k <= i-1 (confirmed), age i-j >= min_swing_age, within lookback."""
    k = p.swing_strength
    out = []
    j0 = max(k, i - p.swing_lookback)
    for j in range(j0, i - max(k, p.min_swing_age) + 1):
        if j + k > i - 1:
            continue
        w = low[j - k:j + k + 1]
        if low[j] <= w.min() and np.count_nonzero(w == low[j]) == 1:
            out.append(j)
    return out


def evaluate_bar(wk, i, p=P):
    """Hit dict if weekly bar i completed a valid sweep, else None. No lookahead."""
    lows = wk["Low"].to_numpy(float)
    op = float(wk["Open"].iloc[i]); hi = float(wk["High"].iloc[i])
    lo = float(wk["Low"].iloc[i]); cl = float(wk["Close"].iloc[i])
    if not all(np.isfinite(x) for x in (op, hi, lo, cl)):
        return None
    rng = hi - lo
    if rng <= 0 or rng > p.max_range_of_close * cl:
        return None
    body = abs(cl - op)
    lower_wick = min(op, cl) - lo
    wick_ratio = lower_wick / rng
    close_in_range = (cl - lo) / rng
    if wick_ratio < p.min_wick_ratio:
        return None
    if lower_wick < p.min_wick_body_mult * max(body, EPS * cl):
        return None
    if close_in_range < p.min_close_in_range:
        return None
    if p.require_green_close and cl <= op:
        return None
    a = _atr(wk, i)

    # liquidity pools: confirmed swings + window low + 52w low (fresh lows allowed)
    pools = []
    for j in _confirmed_swings(lows, i, p):
        pools.append((float(lows[j]), j, False))
    if p.allow_fresh_low and i >= 2:
        wlo_s = max(0, i - p.swing_lookback)
        jw = int(np.nanargmin(lows[wlo_s:i])) + wlo_s
        pools.append((float(lows[jw]), jw, True))
        s52 = max(0, i - 52)
        j52 = int(np.nanargmin(lows[s52:i])) + s52
        pools.append((float(lows[j52]), j52, True))

    best = None; n_pools = 0
    for lev, j, fresh in pools:
        if not np.isfinite(lev) or lev <= 0:
            continue
        if lo >= lev * (1.0 - p.min_depth_pct):
            continue                               # must pierce
        depth = lev - lo
        if depth / lev > p.max_depth_pct:
            continue
        if np.isfinite(a) and depth > p.max_depth_atr_mult * a:
            continue
        if cl <= lev * (1.0 + p.min_close_above_pct):
            continue                               # must reclaim
        n_pools += 1
        if best is None or lev < best[0]:
            best = (lev, j, fresh, depth)
    if best is None:
        return None
    lev, j, fresh, depth = best

    w52 = lows[max(0, i - 52):i]
    is52 = bool(len(w52) and lev <= float(np.nanmin(w52)) * (1 + 1e-6))

    if "Volume" in wk.columns:
        vseq = pd.to_numeric(wk["Volume"], errors="coerce").to_numpy(float)
        vma = np.nanmean(vseq[max(0, i - 20):i]) if i > 0 else np.nan
        vol_ratio = float(vseq[i] / vma) if np.isfinite(vma) and vma > 0 and np.isfinite(vseq[i]) else np.nan
    else:
        vol_ratio = np.nan
    has_vol = np.isfinite(vol_ratio)

    sma20 = float(wk["Close"].rolling(20, min_periods=8).mean().iloc[i])
    sma50 = float(wk["Close"].rolling(50, min_periods=25).mean().iloc[i])

    d = {}
    d["wick"] = _ramp(wick_ratio, p.min_wick_ratio, 0.75)
    d["close_position"] = _ramp(close_in_range, p.min_close_in_range, 0.95) * (1.15 if cl > op else 0.85)
    d["depth"] = _band(depth / max(lev, EPS), 0.002, 0.012, 0.075, 0.16)
    if has_vol:
        d["volume"] = _ramp(vol_ratio, 0.9, 2.6) if vol_ratio >= 1.0 else max(0.0, _ramp(vol_ratio, 0.3, 1.0) * 0.7)
    tr = 0.0
    if np.isfinite(sma20) and sma20 > 0:
        tr += 0.6 if cl >= sma20 else (0.3 if cl >= sma20 * 0.985 else 0.0)
    if np.isfinite(sma50) and sma50 > 0 and np.isfinite(sma20):
        tr += 0.4 if sma20 >= sma50 * 0.98 else 0.0
    d["trend"] = min(1.0, tr)
    d["proximity"] = _band((cl - lo) / max(cl, EPS), 0.005, 0.02, 0.10, 0.17)
    st = 0.90 if is52 else (0.72 if not fresh else 0.62)
    lo52m = float(np.nanmin(lows[max(0, i - 52):i + 1])) if i > 0 else np.nan
    if np.isfinite(lo52m) and lo52m > 0:
        st *= 1.0 - 0.55 * _ramp(cl / lo52m - 1.0, 0.35, 1.10)
    d["structure"] = float(np.clip(st, 0.0, 1.0))
    d["recency"] = 1.0  # evaluated at its own bar

    w = dict(p.weights)
    if not has_vol:                                 # redistribute volume weight
        vw = w.pop("volume")
        tot = sum(w.values())
        w = {k: v * (tot + vw) / tot for k, v in w.items()}
    score = float(np.clip(sum(w.get(k, 0.0) * d.get(k, 0.0) for k in w), 0.0, 100.0))

    return dict(
        i=i, Date=str(wk.index[i].date()), Close=cl, Swept_Level=float(lev),
        Sweep_Low=lo, Swing_Date=str(wk.index[j].date()), Swing_Age_W=int(i - j),
        Pools_Taken=int(n_pools),
        Sweep_Type=("52w-low sweep" if is52 else "new-low sweep" if fresh else "old swing-low sweep"),
        Depth_=100 * depth / lev, Above_=100 * (cl / lev - 1.0),
        Wick_=100 * wick_ratio, ClosePos_=100 * close_in_range,
        Green=bool(cl > op), Vol_x=vol_ratio, SMA20=sma20, SMA50=sma50,
        Trend=bool(np.isfinite(sma20) and cl >= sma20),
        Stop=lo * 0.995, Score=score,
    )


def analyze_latest_weekly(daily_df, p=P, today=None):
    """Sweep hit on the LAST CLOSED weekly candle (production)."""
    wk = weekly_closed(daily_df, today=today)
    n = len(wk)
    if n < max(p.min_weekly_bars, 2 * p.swing_strength + 3):
        return None, None
    rec = evaluate_bar(wk, n - 1, p)
    return rec, wk


def analyze_forming_weekly(daily_df, p=P, today=None):
    """Sweep hit on the CURRENT (still running, unconfirmed) weekly candle, else None.
    Sirf information ke liye — Friday close par hi confirm hota hai."""
    wk_all = to_weekly(daily_df)
    wk_closed = weekly_closed(daily_df, today=today)
    if len(wk_all) == len(wk_closed):
        return None, None            # koi running week nahi
    n = len(wk_all)
    if n < max(p.min_weekly_bars, 2 * p.swing_strength + 3):
        return None, None
    rec = evaluate_bar(wk_all, n - 1, p)
    return rec, wk_all


def detect_all_weekly(daily_df, p=P):
    """Backtest: all weekly bars that completed a sweep (uses all closed weeks)."""
    wk = to_weekly(daily_df)
    n = len(wk)
    out = []
    start = max(p.min_weekly_bars, 2 * p.swing_strength + 3)
    for i in range(start, n):
        rec = evaluate_bar(wk, i, p)
        if rec is not None:
            out.append(rec)
    return out, wk
