"""Friday weekly liquidity-sweep scanner for NSE indices (no constituent stocks)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from index_universe import INDEX_UNIVERSE, symbols_for_history
from market_data import MarketDataError, download_yahoo, history_is_fresh, normalize_yahoo_frame


INDIA_TZ = ZoneInfo("Asia/Kolkata")


def _clean(df):
    """Compatibility wrapper for the shared MultiIndex/OHLC normalizer."""
    return normalize_yahoo_frame(df, interval="1d", require_ohlc=True)


def _weekly(d):
    return d.resample("W-FRI").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna(subset=["Open", "High", "Low", "Close"])


def _swing_lows(w, n=2):
    values = w.Low.to_numpy(float)
    mask = np.zeros(len(values), dtype=bool)
    for i in range(n, len(values) - n):
        mask[i] = values[i] <= values[i - n:i].min() and values[i] < values[i + 1:i + n + 1].min()
    return mask


class WeeklyIndexSweepEngine:
    def __init__(self):
        self.indices_universe = INDEX_UNIVERSE

    @staticmethod
    def is_friday():
        return datetime.now(INDIA_TZ).weekday() == 4

    def scan_weekly_indices(self, lookback_weeks=52):
        try:
            lookback_weeks = int(lookback_weeks)
        except (TypeError, ValueError) as exc:
            raise ValueError("lookback_weeks must be an integer") from exc
        if not 10 <= lookback_weeks <= 104:
            raise ValueError("lookback_weeks must be between 10 and 104")
        hits, near_misses, failed, failure_reasons = [], [], [], []
        run_now = datetime.now(INDIA_TZ)
        run_date = run_now.date()
        friday_close_run = run_now.weekday() == 4
        current_week_is_closed = (
            run_now.weekday() in (5, 6)
            or (run_now.weekday() == 4 and (run_now.hour, run_now.minute) >= (15, 45))
        )

        for item in self.indices_universe:
            used, daily, attempts = None, pd.DataFrame(), []
            for symbol in symbols_for_history(item):
                try:
                    candidate = download_yahoo(
                        symbol, period="2y", interval="1d", timeout=8, attempts=1,
                        require_ohlc=True,
                    )
                    if len(candidate) < 150:
                        raise MarketDataError(f"only {len(candidate)} valid daily bars; 150 required")
                    if not history_is_fresh(candidate, max_age_days=7, reference_date=run_date):
                        raise MarketDataError("latest daily bar is stale or future-dated")
                    daily, used = candidate, symbol
                    break
                except Exception as exc:
                    attempts.append(f"{symbol}: {type(exc).__name__}: {exc}")

            if len(daily) < 150:
                failed.append(item["name"])
                failure_reasons.append({"name": item["name"], "reason": "; ".join(attempts) or "no usable index history"})
                continue

            try:
                bars = _weekly(daily)
                # Exclude the current calendar week's partial candle on Mon–Thu and on
                # Friday before market close. On a weekend, the last Friday candle is
                # already complete and should remain eligible (also useful for diagnostics).
                if len(bars):
                    last_data_week = pd.Timestamp(daily.index[-1]).to_period("W-FRI")
                    current_week = pd.Timestamp(run_date).to_period("W-FRI")
                    if last_data_week == current_week and not current_week_is_closed:
                        bars = bars.iloc[:-1]
                if len(bars) < 30:
                    failed.append(item["name"])
                    failure_reasons.append({"name": item["name"], "reason": f"only {len(bars)} completed weekly bars"})
                    continue
                result = self._evaluate(bars, item, used, lookback_weeks=lookback_weeks)
            except Exception as exc:
                failed.append(item["name"])
                failure_reasons.append({"name": item["name"], "reason": f"analysis: {type(exc).__name__}: {exc}"})
                continue

            if result:
                result["as_of"] = daily.index[-1].date().isoformat()
                (hits if result["has_setup"] else near_misses).append(result)

        hits.sort(key=lambda row: row["score"], reverse=True)
        total = len(self.indices_universe)
        scanned = max(total - len(failed), 0)
        status = "unavailable" if scanned == 0 else "partial" if failed else "ok"
        return {
            "total_scanned": total,
            "scanned_indices": scanned,
            "weekly_hits": hits,
            "near_misses": near_misses,
            "failed_indices": failed,
            "failure_reasons": failure_reasons,
            "scan_date": run_date.isoformat(),
            "is_friday": friday_close_run,
            "status": status,
        }

    def _evaluate(self, w, item, used, lookback_weeks=52):
        if len(w) < 30:
            return None

        i = len(w) - 1
        o, h, low, close = map(float, [w.Open.iloc[i], w.High.iloc[i], w.Low.iloc[i], w.Close.iloc[i]])
        if not all(np.isfinite(value) and value > 0 for value in (o, h, low, close)) or h <= low:
            return None
        candle_range = h - low
        body = abs(close - o)
        lower_wick = min(o, close) - low
        wick_ratio = lower_wick / candle_range
        close_position = (close - low) / candle_range

        swing_mask = _swing_lows(w)
        start_26 = max(0, i - 26)
        start_lookback = max(0, i - int(lookback_weeks))
        pools = [
            (float(w.Low.iloc[j]), "Fractal Swing Low")
            for j in np.flatnonzero(swing_mask)
            if start_26 <= j < i
        ]
        pools.extend([
            (float(w.Low.iloc[start_26:i].min()), "26-Week Low"),
            (float(w.Low.iloc[start_lookback:i].min()), f"{int(lookback_weeks)}-Week Low"),
        ])
        swept = [
            (level, kind)
            for level, kind in pools
            if level > 0 and low < level and close > level and 0.004 <= (level - low) / level <= 0.16
        ]
        if not swept:
            return None

        level, pool_type = min(swept, key=lambda row: row[0])
        depth_pct = (level - low) / level * 100
        delta = w.Close.diff()
        gains = delta.clip(lower=0).rolling(14).mean()
        losses = (-delta.clip(upper=0)).rolling(14).mean()
        relative_strength = gains / losses.replace(0, np.nan)
        rsi = 100 - 100 / (1 + relative_strength)
        rsi_value = float(rsi.iloc[-1]) if np.isfinite(rsi.iloc[-1]) else 50.0
        prior_rsi = rsi.iloc[-15:-1].dropna()
        divergence = (
            close < float(w.Close.iloc[-15:-1].min())
            and not prior_rsi.empty
            and rsi_value > float(prior_rsi.min()) + 1.5
        )
        sma20 = float(w.Close.rolling(20).mean().iloc[-1])
        above_sma20 = close >= sma20

        score = 25
        confluences = [f"{pool_type} Swept & Reclaimed ({depth_pct:.2f}%)"]
        if wick_ratio >= 0.50:
            score += 25
            confluences.append("50%+ Weekly Hammer Wick")
        elif wick_ratio >= 0.35:
            score += 15
            confluences.append("35%+ Weekly Rejection")
        if close_position >= 0.65:
            score += 15
            confluences.append("Close in Upper 35%")
        elif close_position >= 0.50:
            score += 10
            confluences.append("Close in Upper Half")
        if divergence:
            score += 15
            confluences.append("Weekly Bullish RSI Divergence")
        if above_sma20:
            score += 10
            confluences.append("Above Weekly 20 SMA")
        if close >= o:
            score += 10
            confluences.append("Green Weekly Candle")

        valid = wick_ratio >= 0.34 and lower_wick >= 1.15 * body and close_position >= 0.50 and score >= 40
        grade = (
            "🔥 WEEKLY GRADE A+ SWEEP" if score >= 70
            else "⚡ WEEKLY GRADE B SWEEP" if score >= 50
            else "📈 WEEKLY GRADE C SWEEP"
        )
        return {
            "name": item["name"],
            "ticker": used,
            "data_source": "actual_index" if used == item.get("index_symbol") else "index_tracking_etf",
            "category": item["category"],
            "description": item["description"],
            "current_price": round(close, 2),
            "weekly_low": round(low, 2),
            "day_low": round(low, 2),
            "swept_level": round(level, 2),
            "pool_type": pool_type,
            "sweep_depth_pct": round(depth_pct, 2),
            "wick_pct": round(wick_ratio * 100, 1),
            "lower_wick_pct": round(wick_ratio * 100, 1),
            "close_in_range_pct": round(close_position * 100, 1),
            "rsi": round(rsi_value, 1),
            "rsi_divergence": bool(divergence),
            "above_20_sma": bool(above_sma20),
            "is_green": bool(close >= o),
            "score": score,
            "quality_score": score,
            "grade": grade,
            "tier_badge": grade,
            "confluences": confluences,
            "has_setup": valid,
            "is_near_miss": not valid,
            "target_horizon": "2 to 6 Weeks",
            "stop_loss_level": round(low * 0.99, 2),
        }
