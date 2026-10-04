"""Daily liquidity-sweep scanner for NSE indices (no constituent stocks)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from index_universe import INDEX_UNIVERSE, symbols_for_history
from market_data import MarketDataError, download_yahoo, history_is_fresh


INDIA_TZ = ZoneInfo("Asia/Kolkata")


def _clean(frame):
    """Compatibility wrapper returning canonical, valid OHLCV bars."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    from market_data import normalize_yahoo_frame
    return normalize_yahoo_frame(frame, require_ohlc=True)


class IndexSweepEngine:
    def __init__(self):
        self.indices_universe = INDEX_UNIVERSE

    def scan_all_indices(self, lookback_days=60):
        """Backward-compatible signal-only API."""
        return self.scan_all_indices_detailed(lookback_days=lookback_days)["setups"]

    def scan_all_indices_detailed(self, lookback_days=60):
        """Return sweep hits and per-universe feed coverage for truthful reporting."""
        try:
            lookback_days = int(lookback_days)
        except (TypeError, ValueError) as exc:
            raise ValueError("lookback_days must be an integer") from exc
        if not 5 <= lookback_days <= 120:
            raise ValueError("lookback_days must be between 5 and 120")

        reference_date = datetime.now(INDIA_TZ).date()
        setups, failed, scanned, errors = [], [], [], []
        for item in self.indices_universe:
            selected_frame, used_symbol, attempts = pd.DataFrame(), None, []
            for symbol in symbols_for_history(item):
                try:
                    frame = download_yahoo(
                        symbol, period="6mo", interval="1d", timeout=8, attempts=1,
                        require_ohlc=True,
                    )
                    if len(frame) < max(35, lookback_days + 1):
                        raise MarketDataError(f"only {len(frame)} valid daily bars")
                    if not history_is_fresh(frame, max_age_days=7, reference_date=reference_date):
                        raise MarketDataError("latest daily bar is stale or future-dated")
                    selected_frame, used_symbol = frame, symbol
                    break
                except Exception as exc:
                    attempts.append(f"{symbol}: {type(exc).__name__}: {exc}")
            if selected_frame.empty:
                failed.append(item["name"])
                errors.append({"name": item["name"], "reason": "; ".join(attempts) or "no history symbols configured"})
                continue

            scanned.append(item["name"])
            try:
                signal = self._analyze(selected_frame, item, used_symbol, lookback_days=lookback_days)
                if signal and signal.get("has_setup"):
                    signal["as_of"] = selected_frame.index[-1].date().isoformat()
                    setups.append(signal)
            except Exception as exc:
                failed.append(item["name"])
                scanned.remove(item["name"])
                errors.append({"name": item["name"], "reason": f"analysis: {type(exc).__name__}: {exc}"})

        setups.sort(key=lambda row: row["score"], reverse=True)
        total = len(self.indices_universe)
        status = "unavailable" if not scanned else "partial" if failed else "ok"
        return {
            "total_indices": total,
            "scanned_indices": len(scanned),
            "scanned_names": scanned,
            "failed_indices": failed,
            "errors": errors,
            "setups": setups,
            "scan_date": reference_date.isoformat(),
            "status": status,
        }

    def scan_all_indices_sweeps(self, lookback_days=60):
        """Legacy alias retained for callers expecting only the signal list."""
        return self.scan_all_indices(lookback_days=lookback_days)

    def _analyze(self, df, item, used, lookback_days=60):
        if df is None or len(df) < max(35, int(lookback_days) + 1):
            return {"name": item["name"], "has_setup": False}
        if not {"Open", "High", "Low", "Close"}.issubset(df.columns):
            return {"name": item["name"], "has_setup": False}

        today, previous = df.iloc[-1], df.iloc[-2]
        o, high, low, close = map(float, [today.Open, today.High, today.Low, today.Close])
        if not all(np.isfinite(value) and value > 0 for value in (o, high, low, close)):
            return {"name": item["name"], "has_setup": False}
        candle_range = high - low
        if candle_range <= 0:
            return {"name": item["name"], "has_setup": False}
        wick = (min(o, close) - low) / candle_range

        delta = df.Close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        relative_strength = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + relative_strength)
        if pd.isna(rsi.iloc[-1]):
            rsi_value = 100.0 if gain.iloc[-1] > 0 and loss.iloc[-1] == 0 else 50.0
        else:
            rsi_value = float(rsi.iloc[-1])

        prior = df.iloc[-(int(lookback_days) + 1):-1]
        if prior.empty:
            return {"name": item["name"], "has_setup": False}
        swing_level = float(prior.Low.min())
        prior_close_low = float(prior.Close.min())
        major_sweep = low < swing_level and close > swing_level and wick >= 0.30
        prior_day_low = float(previous.Low)
        pdl_sweep = low < prior_day_low and close > prior_day_low and wick >= 0.35
        prior_rsi = rsi.iloc[-15:-1].dropna()
        divergence = (
            low < prior_close_low
            and not prior_rsi.empty
            and rsi_value > float(prior_rsi.min()) + 1.5
            and rsi_value < 60
        )
        fvg_bottom = float(df.High.iloc[-3])
        fvg = low > fvg_bottom
        ema20 = float(df.Close.ewm(span=20, adjust=False).mean().iloc[-1])
        above_ema = close >= ema20

        if not (major_sweep or pdl_sweep):
            return {"name": item["name"], "has_setup": False}
        score, confluences = 0, []
        level = swing_level
        if major_sweep:
            score += 40
            confluences.append(f"{int(lookback_days)}-Session Swing Low Swept & Reclaimed")
        else:
            score += 25
            level = prior_day_low
            confluences.append("Prior Day Low Swept & Reclaimed")
        if wick >= 0.50:
            score += 20
            confluences.append("Massive 50%+ Lower-Wick Absorption")
        elif wick >= 0.35:
            score += 10
            confluences.append("Strong 35%+ Lower Rejection")
        if divergence:
            score += 20
            confluences.append("Bullish RSI Divergence")
        if fvg:
            score += 10
            confluences.append("Bullish Fair Value Gap")
        if above_ema:
            score += 10
            confluences.append("Above 20 EMA")
        if score < 35 or level <= 0:
            return {"name": item["name"], "has_setup": False}

        grade = "🔥 GRADE A+ SWEEP" if score >= 70 else "⚡ GRADE B SWEEP" if score >= 50 else "📈 GRADE C SWEEP"
        return {
            "name": item["name"],
            "ticker": used,
            "data_source": "actual_index" if used == item.get("index_symbol") else "index_tracking_etf",
            "category": item["category"],
            "description": item["description"],
            "current_price": round(close, 2),
            "swept_level": round(level, 2),
            "day_low": round(low, 2),
            "lower_wick_pct": round(wick * 100, 1),
            "rsi": round(rsi_value, 1),
            "rsi_divergence": bool(divergence),
            "fvg_detected": bool(fvg),
            "fvg_top": round(low, 2) if fvg else 0,
            "fvg_bottom": round(fvg_bottom, 2) if fvg else 0,
            "above_20_ema": bool(above_ema),
            "sweep_depth_pct": round(max(0, (level - low) / level * 100), 2),
            "quality_score": score,
            "score": score,
            "grade": grade,
            "tier_badge": grade,
            "confluences": confluences,
            "has_setup": True,
            "action": f"Bullish index reversal watch; invalidation below {low * 0.995:.2f}.",
        }
