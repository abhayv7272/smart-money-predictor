"""Render compact, email-safe candlestick charts for index sweep signals."""
from __future__ import annotations

import base64
import io
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from market_data import download_yahoo, history_is_fresh, normalize_yahoo_frame

COLORS = {
    "bg": "#030712", "panel": "#0B1120", "grid": "#1E293B", "text": "#CBD5E1",
    "up": "#10B981", "down": "#EF4444", "level": "#F59E0B", "entry": "#38BDF8", "target": "#A78BFA",
}


def _clean(frame, interval="1d"):
    """Compatibility wrapper for the same MultiIndex/OHLC policy as the scanners."""
    return normalize_yahoo_frame(
        frame,
        interval=interval,
        intraday_timezone="Asia/Kolkata" if interval != "1d" else None,
        require_ohlc=True,
    )


def _fetch(ticker, kind):
    if kind == "weekly":
        data = download_yahoo(ticker, period="2y", interval="1d", timeout=8, require_ohlc=True)
        if not history_is_fresh(data, max_age_days=7, reference_date=datetime.now(ZoneInfo("Asia/Kolkata")).date()):
            return pd.DataFrame()
        return data.resample("W-FRI").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
        }).dropna(subset=["Open", "High", "Low", "Close"]).tail(32)
    if kind == "mtf":
        data = download_yahoo(
            ticker, period="10d", interval="15m", timeout=8,
            intraday_timezone="Asia/Kolkata", require_ohlc=True,
        )
        return data.tail(130)
    data = download_yahoo(ticker, period="6mo", interval="1d", timeout=8, require_ohlc=True)
    if not history_is_fresh(data, max_age_days=7, reference_date=datetime.now(ZoneInfo("Asia/Kolkata")).date()):
        return pd.DataFrame()
    return data.tail(55)


def render_signal_chart(signal, kind="daily"):
    """Return a PNG data URI; chart-feed errors remain presentation-only."""
    ticker = signal.get("ticker")
    if not ticker:
        return ""
    try:
        data = _fetch(ticker, kind)
    except Exception:
        return ""
    if len(data) < 5:
        return ""
    if kind == "mtf":
        data = data.tail(80)

    fig, ax = plt.subplots(figsize=(10, 3.8), dpi=120)
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_facecolor(COLORS["panel"])
    width = 0.62
    for i, (_, row) in enumerate(data.iterrows()):
        open_price, high, low, close = map(float, [row.Open, row.High, row.Low, row.Close])
        color = COLORS["up"] if close >= open_price else COLORS["down"]
        ax.vlines(i, low, high, color=color, linewidth=0.8, alpha=0.9)
        bottom = min(open_price, close)
        height = max(abs(close - open_price), max(abs(close) * 0.0002, 1e-8))
        ax.add_patch(Rectangle((i - width / 2, bottom), width, height, facecolor=color, edgecolor=color, linewidth=0.5))

    if kind == "daily":
        lines = [("Swept", signal.get("swept_level"), COLORS["level"]),
                 ("Invalidation", signal.get("day_low"), COLORS["down"])]
    elif kind == "weekly":
        lines = [("Weekly pool", signal.get("swept_level"), COLORS["level"]),
                 ("SL", signal.get("stop_loss_level"), COLORS["down"])]
    else:
        lines = [("PWL", signal.get("pwl"), COLORS["level"]),
                 ("Entry/MSS", signal.get("entry"), COLORS["entry"]),
                 ("SL", signal.get("stoploss"), COLORS["down"]),
                 ("T1", signal.get("target_1"), COLORS["up"]),
                 ("T2/PWH", signal.get("target_2"), COLORS["target"])]
    for label, value, color in lines:
        if value is None:
            continue
        try:
            level = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(level):
            continue
        ax.axhline(level, color=color, linewidth=1, linestyle="--", alpha=0.9)
        ax.text(
            len(data) - 0.5, level, f" {label} {level:,.2f}", color=color, fontsize=7, va="center", ha="left",
            bbox=dict(facecolor=COLORS["bg"], edgecolor="none", alpha=0.75, pad=1),
        )

    title = f"{signal.get('name', 'Index')} • {kind.upper()} SIGNAL CHART • {ticker}"
    ax.set_title(title, color="#F8FAFC", fontsize=10, fontweight="bold", loc="left", pad=8)
    ax.grid(True, color=COLORS["grid"], alpha=0.45, linewidth=0.5)
    ax.tick_params(colors=COLORS["text"], labelsize=7)
    for spine in ax.spines.values():
        spine.set_color(COLORS["grid"])
    count = len(data)
    step = max(1, count // 6)
    ticks = list(range(0, count, step))
    ax.set_xticks(ticks)
    labels = []
    for index in ticks:
        timestamp = pd.Timestamp(data.index[index])
        labels.append(timestamp.strftime("%d %b\n%H:%M") if kind == "mtf" else timestamp.strftime("%d %b"))
    ax.set_xticklabels(labels)
    ax.set_xlim(-1, count + 11)
    fig.tight_layout(pad=1)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def chart_html(signal, kind):
    uri = render_signal_chart(signal, kind)
    if not uri:
        return '<div style="color:#64748B;font-size:11px;margin-top:8px">Chart data temporarily unavailable.</div>'
    return (
        f'<img src="{uri}" alt="{signal.get("name", "Index")} {kind} signal chart" '
        'style="width:100%;max-width:980px;height:auto;border-radius:8px;border:1px solid #1E293B;margin-top:10px;display:block">'
    )
