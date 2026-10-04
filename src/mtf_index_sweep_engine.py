"""Index-only adaptation of the Colab MTF BUY-side sweep/MSS framework.

The engine scans NSE index symbols only and uses a shared, defensive Yahoo data
normalizer. A missing daily or 15-minute feed is surfaced explicitly, not counted as
an ordinary no-signal result.
"""
from __future__ import annotations

from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd

from index_universe import INDEX_UNIVERSE, symbols_for_history
from market_data import MarketDataError, download_yahoo, history_is_fresh, normalize_yahoo_frame

SWING_WINDOW = 2
SL_BUFFER_PCT = 0.002
MIN_RR_T2 = 1.0
INDIA_TZ = ZoneInfo("Asia/Kolkata")


def _flat(df: pd.DataFrame, interval="1d") -> pd.DataFrame:
    """Compatibility wrapper returning canonical, valid OHLCV rows."""
    return normalize_yahoo_frame(
        df,
        interval=interval,
        intraday_timezone="Asia/Kolkata" if interval != "1d" else None,
        require_ohlc=True,
    )


def _ref_date() -> date:
    now = datetime.now(INDIA_TZ)
    if now.weekday() == 5:
        return (now - timedelta(days=1)).date()
    if now.weekday() == 6:
        return (now - timedelta(days=2)).date()
    if (now.hour, now.minute) < (15, 30):
        now -= timedelta(days=1)
        while now.weekday() >= 5:
            now -= timedelta(days=1)
    return now.date()


def _weekly_levels(daily: pd.DataFrame, ref: date) -> Tuple[Optional[float], Optional[float]]:
    x = _flat(daily)
    x = x[x.index.date <= ref]
    if len(x) < 10:
        return None, None
    weekly = x.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
    }).dropna(subset=["Open", "High", "Low", "Close"])
    if len(weekly) < 2:
        return None, None
    previous = weekly.iloc[-2]
    return float(previous.High), float(previous.Low)


def _current_week(df: pd.DataFrame, ref: date) -> pd.DataFrame:
    x = _flat(df)
    monday = ref - timedelta(days=ref.weekday())
    return x[(x.index.date >= monday) & (x.index.date <= ref)]


def _swing_highs(df: pd.DataFrame, n: int = 2) -> List[int]:
    out = []
    for i in range(n, len(df) - n):
        high = float(df.High.iloc[i])
        if np.all(high > df.High.iloc[i - n:i].values) and np.all(high > df.High.iloc[i + 1:i + n + 1].values):
            out.append(i)
    return out


class MTFIndexSweepEngine:
    """Previous-week PWL → daily reclaim → causal current-week 15m bullish MSS."""

    def scan_all_indices(self) -> Dict[str, object]:
        reference_date = _ref_date()
        results, errors, failed_indices, scanned_indices = [], [], [], []

        for item in INDEX_UNIVERSE:
            name, category = item["name"], item["category"]
            daily, ticker, attempts = pd.DataFrame(), None, []
            for candidate in symbols_for_history(item):
                try:
                    probe = download_yahoo(
                        candidate, period="6mo", interval="1d", timeout=8, attempts=1,
                        require_ohlc=True,
                    )
                    if len(probe) < 30:
                        raise MarketDataError(f"only {len(probe)} valid daily bars; 30 required")
                    if not history_is_fresh(probe, max_age_days=4, reference_date=reference_date):
                        raise MarketDataError("latest daily bar is stale or future-dated")
                    daily, ticker = probe, candidate
                    break
                except Exception as exc:
                    attempts.append(f"{candidate}: {type(exc).__name__}: {exc}")

            if daily.empty:
                failed_indices.append(name)
                errors.append({"name": name, "timeframe": "1d", "reason": "; ".join(attempts) or "no history symbols configured"})
                continue
            scanned_indices.append(name)

            pwh, pwl = _weekly_levels(daily, reference_date)
            if pwh is None or pwl is None or pwl <= 0:
                failed_indices.append(name)
                scanned_indices.remove(name)
                errors.append({"name": name, "timeframe": "1d", "reason": "not enough valid weekly candles/levels"})
                continue
            current_week = _current_week(daily, reference_date)
            if current_week.empty:
                continue

            week_low = float(current_week.Low.min())
            close = float(current_week.Close.iloc[-1])
            # Preserve the notebook's BUY-only previous-week-low trap condition.
            if not (week_low < pwl and close > pwl):
                continue

            active = current_week.Low.cummin().lt(pwl) & current_week.Close.gt(pwl)
            starts = active & ~active.shift(1, fill_value=False)
            positions = np.flatnonzero(starts.to_numpy())
            if not len(positions):
                continue
            confirmation = current_week.index[int(positions[-1])].normalize() + pd.Timedelta(hours=15, minutes=30)
            row = {
                "name": name,
                "ticker": ticker,
                "data_source": "actual_index" if ticker == item.get("index_symbol") else "index_tracking_etf",
                "category": category,
                "status": "DAILY_TRAP_CONFIRMED",
                "pwh": round(pwh, 2),
                "pwl": round(pwl, 2),
                "week_low": round(week_low, 2),
                "latest_close": round(close, 2),
                "trap_confirmation_time": str(confirmation),
                "entry": None,
                "stoploss": None,
                "target_1": None,
                "target_2": round(pwh, 2),
                "rr_t2": None,
                "mss_time": None,
                "fresh_trigger": False,
                "daily_as_of": daily.index[-1].date().isoformat(),
            }

            try:
                intraday = download_yahoo(
                    ticker, period="10d", interval="15m", timeout=8, attempts=1,
                    intraday_timezone="Asia/Kolkata", require_ohlc=True,
                )
            except Exception as exc:
                row["status"] = "PENDING_15M_DATA"
                errors.append({"name": name, "timeframe": "15m", "reason": f"{type(exc).__name__}: {exc}"})
                results.append(row)
                continue

            monday = pd.Timestamp(reference_date - timedelta(days=reference_date.weekday()))
            end = pd.Timestamp(reference_date) + pd.Timedelta(days=1)
            if not intraday.empty:
                regular = (
                    (intraday.index.time >= pd.Timestamp("09:15").time())
                    & (intraday.index.time < pd.Timestamp("15:30").time())
                )
                intraday = intraday[(intraday.index >= monday) & (intraday.index < end) & regular]
            if intraday.empty or not history_is_fresh(intraday, max_age_days=0, reference_date=reference_date):
                row["status"] = "PENDING_15M_DATA"
                errors.append({"name": name, "timeframe": "15m", "reason": "no fresh current-week regular-session bars"})
                results.append(row)
                continue
            row["intraday_as_of"] = intraday.index[-1].date().isoformat()
            if len(intraday) < 20:
                row["status"] = "PENDING_15M_DATA"
                errors.append({"name": name, "timeframe": "15m", "reason": f"only {len(intraday)} current-week regular bars"})
                results.append(row)
                continue

            candles = intraday.reset_index()
            candles.rename(columns={candles.columns[0]: "_Time"}, inplace=True)
            swept = candles.Low < pwl
            if not swept.any():
                row["status"] = "PENDING_MSS"
                results.append(row)
                continue

            extreme_pos = int(candles.loc[swept, "Low"].idxmin())
            trough = float(candles.loc[extreme_pos, "Low"])
            swing_positions = _swing_highs(candles.iloc[:extreme_pos + 1], SWING_WINDOW)
            if not swing_positions:
                row["status"] = "PENDING_SWING_STRUCTURE"
                results.append(row)
                continue

            swing_pos = swing_positions[-1]
            trigger = float(candles.loc[swing_pos, "High"])
            stop = trough * (1 - SL_BUFFER_PCT)
            risk = trigger - stop
            target_1 = trigger + risk
            post = candles.iloc[extreme_pos + 1:]
            post = post[post["_Time"] > confirmation]
            hit = post.Close > trigger
            row.update(
                entry=round(trigger, 2),
                stoploss=round(stop, 2),
                target_1=round(target_1, 2),
                target_2=round(pwh, 2),
                rr_t2=round((pwh - trigger) / risk, 2) if risk > 0 else None,
            )
            if hit.any():
                mss_pos = int(post.loc[hit].index[0])
                mss_time = pd.Timestamp(candles.loc[mss_pos, "_Time"])
                row.update(
                    status=("TRIGGERED_ACTIVE" if row["rr_t2"] is not None and row["rr_t2"] >= MIN_RR_T2
                            else "FILTERED_LOW_RR"),
                    mss_time=str(mss_time),
                    mss_close=round(float(candles.loc[mss_pos, "Close"]), 2),
                    fresh_trigger=(mss_time.date() == reference_date),
                )
            else:
                row["status"] = "PENDING_MSS"
            results.append(row)

        actionable = [row for row in results if row["status"] in ("TRIGGERED_ACTIVE", "PENDING_MSS", "DAILY_TRAP_CONFIRMED")]
        triggered = [row for row in results if row["status"] == "TRIGGERED_ACTIVE"]
        total = len(INDEX_UNIVERSE)
        covered = len(scanned_indices)
        status = "unavailable" if covered == 0 else "partial" if failed_indices or errors else "ok"
        return {
            "reference_date": str(reference_date),
            "total_indices": total,
            "scanned_indices": covered,
            "failed_indices": failed_indices,
            "setups": results,
            "actionable": actionable,
            "triggered": triggered,
            "has_signals": bool(actionable),
            "errors": errors,
            "status": status,
        }
