#!/usr/bin/env python3
"""
LIQUIDITY SWEEP ENGINE — index edition.
Ported from the user's Colab 'NSE Liquidity Sweep Screener' (stocks) and adapted for indices:
 - volume confirmation optional (many indices lack reliable volume; score re-weighted)
 - same 7 hard rules: fractal swing low, pierce, reclaim, proper wick, depth cap,
   bullish close, prior close above level
 - detect_all(): runs detection on EVERY bar (for backtesting), analyze_latest(): last bar only
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class SweepConfig:
    min_bars: int = 60
    fractal_k: int = 2            # 5-bar fractal
    level_lookback: int = 120     # level age cap (bars)
    level_dedup_pct: float = 0.0015
    min_pierce_pct: float = 0.0005
    close_above_buffer: float = 0.001
    max_sweep_depth: float = 0.025
    min_wick_ratio: float = 0.30
    min_wick_pct_price: float = 0.0015
    require_bullish_close: bool = True
    require_prior_above: bool = True
    volume_lookback: int = 20
    rsi_period: int = 14


CFG = SweepConfig()


def find_swing_lows(low, k):
    n = len(low)
    out = []
    for i in range(k, n - k):
        w = low[i - k:i + k + 1]
        if low[i] <= w.min() and np.count_nonzero(w == low[i]) == 1:
            out.append((i, float(low[i])))
    return out


def merge_pools(swings, dedup_pct):
    pools = []
    for i, L in swings:
        for p in pools:
            if abs(L - p[0]) / p[0] <= dedup_pct:
                p[0] = min(p[0], L)
                p[2] = max(p[2], i)
                break
        else:
            pools.append([L, i, i])
    return pools


def rsi_wilder(close, period=14):
    delta = np.diff(close)
    gain = pd.Series(np.clip(delta, 0, None)).ewm(alpha=1 / period, adjust=False).mean()
    loss = pd.Series(np.clip(-delta, 0, None)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0)


def _check_bar(o, h, l, c, v, T, pools, cfg):
    """Hard-filter check of bar T against liquidity pools. Returns best pool dict or None."""
    if not (np.isfinite(o[T]) and np.isfinite(c[T]) and h[T] > 0):
        return None
    rng = h[T] - l[T]
    if rng <= 0:
        return None
    lw = min(o[T], c[T]) - l[T]
    best = None
    for level, first_i, last_i in pools:
        age = T - first_i
        if age <= 0 or age > cfg.level_lookback:
            continue
        if l[T] >= level * (1 - cfg.min_pierce_pct):
            continue
        if c[T] <= level * (1 + cfg.close_above_buffer):
            continue
        depth = (level - l[T]) / level
        if depth > cfg.max_sweep_depth:
            continue
        if lw / rng < cfg.min_wick_ratio:
            continue
        if lw < cfg.min_wick_pct_price * level:
            continue
        if cfg.require_bullish_close and c[T] <= o[T]:
            continue
        if cfg.require_prior_above and c[T - 1] <= level:
            continue
        key = (depth, -age)
        if best is None or key < (best["depth"], -best["age"]):
            best = dict(level=level, age=age, touch_ago=T - last_i, depth=depth)
    return best


def _score_bar(o, h, l, c, v, T, best, cfg):
    """Score 0-100. Volume part auto-disabled (re-weighted) when volume data absent."""
    rng = h[T] - l[T]
    lw = min(o[T], c[T]) - l[T]
    wick_ratio = lw / rng
    close_pos = (c[T] - l[T]) / rng
    rsi = float(rsi_wilder(c[:T + 1], cfg.rsi_period).iloc[-1])
    e20 = float(pd.Series(c[:T + 1]).ewm(span=20, adjust=False).mean().iloc[-1])
    e50 = float(pd.Series(c[:T + 1]).ewm(span=50, adjust=False).mean().iloc[-1])

    has_vol = v is not None and np.isfinite(v[T]) and v[max(0, T - cfg.volume_lookback):T].sum() > 0
    if has_vol:
        vol_base = float(np.nanmean(v[T - cfg.volume_lookback:T]))
        vol_x = float(v[T]) / vol_base if vol_base > 0 else 1.0
    else:
        vol_x = np.nan

    s_wick = min(wick_ratio / 0.75, 1.0)
    s_close = max(0.0, min(1.0, (close_pos - 0.5) / 0.45))
    s_depth = max(0.0, 1.0 - best["depth"] / cfg.max_sweep_depth)
    if has_vol:
        if vol_x <= 1.0:
            s_vol = 0.5 * vol_x
        elif vol_x <= 3.0:
            s_vol = 0.5 + 0.5 * (vol_x - 1.0) / 2.0
        else:
            s_vol = max(0.0, 1.0 - (vol_x - 3.0) / 4.0)
    else:
        s_vol = None
    if rsi <= 30:
        s_rsi = 1.0
    elif rsi <= 55:
        s_rsi = 1.0 - (rsi - 30) / 50.0
    else:
        s_rsi = max(0.0, 0.5 - (rsi - 55) / 60.0)
    s_trend = (0.6 if c[T] > e50 else 0.0) + (0.4 if c[T] > e20 else 0.0)

    if s_vol is None:
        # weights: wick 30, close 20, depth 17.5, rsi 17.5, trend 15  (vol redistributed)
        score = 100 * (0.30 * s_wick + 0.20 * s_close + 0.175 * s_depth
                       + 0.175 * s_rsi + 0.15 * s_trend)
    else:
        # original weighting: wick 25, close 15, depth 15, vol 15, rsi 15, trend 15
        score = 100 * (0.25 * s_wick + 0.15 * s_close + 0.15 * s_depth
                       + 0.15 * s_vol + 0.15 * s_rsi + 0.15 * s_trend)

    stop = float(l[T])
    target_ref = max(float(np.max(h[max(0, T - 20):T])), float(c[T]) * 1.01)
    rr = max(0.0, (target_ref - c[T]) / max(c[T] - stop, 1e-9))
    return dict(
        Close=float(c[T]), Swept_Level=float(best["level"]), Level_Age_Bars=int(best["age"]),
        Touch_Ago_Bars=int(best["touch_ago"]), Sweep_Depth_=100 * best["depth"],
        Above_Level_=100 * (c[T] / best["level"] - 1.0), LowerWick_=100 * wick_ratio,
        ClosePos_=100 * close_pos, Vol_x=float(vol_x) if has_vol else np.nan,
        RSI14=rsi, E20=bool(c[T] > e20), E50=bool(c[T] > e50),
        Stop_Loss=stop, Target_Ref=target_ref, RR=rr, Score=float(score),
    )


def analyze_latest(df, cfg=CFG):
    """Setup record if the LATEST candle completed a valid sweep, else None."""
    n = len(df)
    if n < max(cfg.min_bars, 2 * cfg.fractal_k + 4):
        return None
    o = df["Open"].to_numpy(float); h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float); c = df["Close"].to_numpy(float)
    v = df["Volume"].to_numpy(float) if "Volume" in df.columns else None
    T = n - 1
    # fractals must be confirmed k bars later -> exclude last k bars as levels
    pools = merge_pools(find_swing_lows(l[:T - cfg.fractal_k + 1], cfg.fractal_k),
                        cfg.level_dedup_pct)
    best = _check_bar(o, h, l, c, v, T, pools, cfg)
    if best is None:
        return None
    rec = _score_bar(o, h, l, c, v, T, best, cfg)
    rec["Date"] = str(df.index[T].date()) if hasattr(df.index[T], "date") else str(df.index[T])
    return rec


def detect_all(df, cfg=CFG):
    """Backtest helper: list of (T, record) for every bar that completed a sweep.
    NO LOOKAHEAD: levels for bar T use only lows up to T-k (fractal needs k future bars
    to confirm, so a fractal at i is only usable from bar i+k onwards)."""
    n = len(df)
    o = df["Open"].to_numpy(float); h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float); c = df["Close"].to_numpy(float)
    v = df["Volume"].to_numpy(float) if "Volume" in df.columns else None
    k = cfg.fractal_k
    hits = []
    for T in range(max(cfg.min_bars, 2 * k + 4), n):
        swings = find_swing_lows(l[:T - k + 1], k)   # fractal at i needs l[i+k] known: i+k <= T-? 
        # find_swing_lows on l[:T-k+1] yields fractals with centre <= T-2k... conservative & safe
        pools = merge_pools(swings, cfg.level_dedup_pct)
        best = _check_bar(o, h, l, c, v, T, pools, cfg)
        if best is not None:
            rec = _score_bar(o, h, l, c, v, T, best, cfg)
            rec["T"] = T
            rec["Date"] = str(df.index[T].date()) if hasattr(df.index[T], "date") else str(df.index[T])
            hits.append(rec)
    return hits
