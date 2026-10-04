"""NIFTY 1–3 month scenario overlay based on the supplied NIFTY Scenario Lab model.

The frozen model weights/statistics live in data/nifty_scenario_lab/model_data.json.
Current features are recalculated from Yahoo Finance on every run; the old embedded
snapshot in the source archive is deliberately not used as a live-data fallback.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from market_data import download_yahoo, history_is_fresh, normalize_yahoo_frame


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DATA = ROOT / "data" / "nifty_scenario_lab" / "model_data.json"
TICKERS = {
    "^NSEI": "nifty",
    "^INDIAVIX": "india_vix",
    "^VIX": "us_vix",
}


class ScenarioDataError(ValueError):
    """Raised when live history cannot support a valid scenario calculation."""


class NiftyScenarioEngine:
    """Recalculate the supplied lab model using current, look-ahead-safe inputs."""

    def __init__(self, model_data_path: str | Path | None = None):
        self.model_data_path = Path(model_data_path) if model_data_path else DEFAULT_MODEL_DATA
        with self.model_data_path.open("r", encoding="utf-8") as handle:
            self.model_data = json.load(handle)
        self._validate_model_data()

    def _validate_model_data(self) -> None:
        model = self.model_data.get("model", {})
        required = {"scaler_mean", "scaler_scale", "y_up_1M", "y_up_3M", "y_dip5_3M", "y_rally5_3M"}
        if not required.issubset(model):
            raise ValueError(f"Scenario model data is missing: {', '.join(sorted(required - set(model)))}")
        if len(model["scaler_mean"]) != 5 or len(model["scaler_scale"]) != 5:
            raise ValueError("Scenario model expects exactly five calibrated input features.")

    @staticmethod
    def _close_series(frame: pd.DataFrame, ticker: str) -> pd.Series:
        """Extract one ticker's Close series through the shared Yahoo normalizer."""
        if ticker not in TICKERS:
            raise ScenarioDataError(f"Unsupported scenario ticker {ticker}.")
        normalized = normalize_yahoo_frame(frame, symbol=ticker, interval="1d")
        if normalized.empty or "Close" not in normalized:
            raise ScenarioDataError(f"Yahoo Finance returned no valid Close history for {ticker}.")
        close = normalized["Close"].astype(float)
        close.name = TICKERS[ticker]
        return close

    def _fetch_history(self) -> pd.DataFrame:
        """Download bounded, fresh daily closes and align them to Indian sessions."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        series = []
        reference_date = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        for ticker, column_name in TICKERS.items():
            downloaded = download_yahoo(
                ticker, period="3y", interval="1d", timeout=10, attempts=1,
            )
            if not history_is_fresh(downloaded, max_age_days=7, reference_date=reference_date):
                raise ScenarioDataError(f"Yahoo Finance history for {ticker} is stale or future-dated.")
            close = downloaded["Close"].copy()
            close.name = column_name
            series.append(close)

        prices = pd.concat(series, axis=1).sort_index()
        if "nifty" not in prices or prices["nifty"].dropna().empty:
            raise ScenarioDataError("NIFTY 50 history is unavailable.")
        # Keep missing rows visible here. build_inputs checks actual VIX last-observation
        # dates before applying its bounded historical forward-fill.
        india_sessions = prices.index[prices["nifty"].notna()]
        return prices.reindex(india_sessions)

    @staticmethod
    def build_inputs(history: pd.DataFrame) -> dict[str, Any]:
        """Calculate the five model inputs and scenario atoms from aligned daily closes.

        `history` must have `nifty`, `india_vix`, and `us_vix` columns on the Indian
        trading calendar. US VIX is shifted one row here so callers cannot accidentally
        feed the same-night US close into an Indian-session forecast.
        """
        if history is None or history.empty:
            raise ScenarioDataError("No aligned market history was supplied.")
        missing = {"nifty", "india_vix", "us_vix"} - set(history.columns)
        if missing:
            raise ScenarioDataError(f"Missing scenario history columns: {', '.join(sorted(missing))}.")

        prices = history[["nifty", "india_vix", "us_vix"]].copy().sort_index()
        for column in prices.columns:
            prices[column] = pd.to_numeric(prices[column], errors="coerce")
        prices = prices.replace([float("inf"), float("-inf")], float("nan"))
        prices.loc[prices["nifty"] <= 0, "nifty"] = float("nan")
        prices.loc[prices["india_vix"] <= 0, "india_vix"] = float("nan")
        prices.loc[prices["us_vix"] <= 0, "us_vix"] = float("nan")
        prices = prices.loc[prices["nifty"].notna()]
        if len(prices) < 253:
            raise ScenarioDataError(f"Need at least 253 NIFTY sessions; received {len(prices)}.")

        latest_nifty_date = prices.index[-1]
        latest_india_vix_date = prices["india_vix"].last_valid_index()
        if latest_india_vix_date is None or latest_india_vix_date != latest_nifty_date:
            raise ScenarioDataError("India VIX is missing on the latest NIFTY session; refusing a stale scenario.")
        latest_us_vix_date = prices["us_vix"].last_valid_index()
        if latest_us_vix_date is None or (latest_nifty_date - latest_us_vix_date).days > 7:
            raise ScenarioDataError("US VIX history is stale relative to the latest NIFTY session.")

        prices = prices.ffill(limit=5)
        nifty = prices["nifty"].dropna()
        india_vix = prices["india_vix"].ffill(limit=5)
        us_vix = prices["us_vix"].ffill(limit=5).shift(1)
        if india_vix.iloc[-1] <= 0 or pd.isna(india_vix.iloc[-1]):
            raise ScenarioDataError("Latest India VIX value is unavailable.")
        if us_vix.iloc[-1] <= 0 or pd.isna(us_vix.iloc[-1]):
            raise ScenarioDataError("Lagged US VIX value is unavailable.")
        if nifty.iloc[-1] <= 0:
            raise ScenarioDataError("Latest NIFTY 50 value is invalid.")

        def percentile_against_prior(series: pd.Series) -> float:
            current = float(series.iloc[-1])
            prior = series.iloc[-253:-1].dropna()
            if len(prior) < 252:
                raise ScenarioDataError("At least 252 prior VIX observations are required.")
            return float((current > prior).mean() * 100.0)

        current = float(nifty.iloc[-1])
        ivix_pct = percentile_against_prior(india_vix)
        uvix_pct = percentile_against_prior(us_vix)
        ema50 = nifty.ewm(span=50, adjust=False).mean()
        ema200 = nifty.ewm(span=200, adjust=False).mean()
        dist200 = 100.0 * (current / float(ema200.iloc[-1]) - 1.0)
        drawdown_252 = 100.0 * (current / float(nifty.iloc[-252:].max()) - 1.0)
        distance_6m_low = 100.0 * (current / float(nifty.iloc[-126:].min()) - 1.0)

        delta = nifty.diff()
        gains = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        losses = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        latest_gain, latest_loss = float(gains.iloc[-1]), float(losses.iloc[-1])
        if latest_loss == 0:
            rsi14 = 100.0 if latest_gain > 0 else 50.0
        else:
            rsi14 = 100.0 - 100.0 / (1.0 + latest_gain / latest_loss)

        weekly_close = nifty.resample("W-FRI").last().dropna()
        weekly_ema30 = float(weekly_close.ewm(span=30, adjust=False).mean().iloc[-1])
        macd = nifty.ewm(span=12, adjust=False).mean() - nifty.ewm(span=26, adjust=False).mean()
        macd_histogram = macd - macd.ewm(span=9, adjust=False).mean()
        atoms = {
            "ema200": current > float(ema200.iloc[-1]),
            "ema50": current > float(ema50.iloc[-1]),
            "golden": float(ema50.iloc[-1]) > float(ema200.iloc[-1]),
            "weekly": current > weekly_ema30,
            "rsi60": rsi14 > 60.0,
            "macd_pos": float(macd_histogram.iloc[-1]) > 0.0,
            "bothvixlow": ivix_pct < 30.0 and uvix_pct < 30.0,
        }

        return {
            "nifty": round(current, 2),
            "india_vix": round(float(india_vix.iloc[-1]), 2),
            "india_vix_pct": round(ivix_pct, 1),
            "us_vix": round(float(us_vix.iloc[-1]), 2),
            "us_vix_pct": round(uvix_pct, 1),
            "rsi14": round(rsi14, 1),
            "dist200": round(dist200, 2),
            "dd252": round(drawdown_252, 2),
            "dist6mlow": round(distance_6m_low, 2),
            "bull_count": int(sum(atoms.values())),
            "atoms": atoms,
            "as_of": pd.Timestamp(nifty.index[-1]).date().isoformat(),
        }

    def _predict_probabilities(self, inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        model = self.model_data["model"]
        x = [
            inputs["india_vix_pct"],
            inputs["us_vix_pct"],
            inputs["dd252"],
            inputs["dist200"],
            inputs["bull_count"],
        ]
        standardized = [
            (float(xi) - float(mean)) / float(scale)
            for xi, mean, scale in zip(x, model["scaler_mean"], model["scaler_scale"])
        ]
        probabilities: dict[str, dict[str, float]] = {}
        for target in ("y_up_1M", "y_up_3M", "y_dip5_3M", "y_rally5_3M"):
            parameters = model[target]
            z = sum(float(weight) * standardized[i] for i, weight in enumerate(parameters["w"]))
            z += float(parameters["b"])
            raw = self._sigmoid(z)
            calibration = self.model_data["calibration"][target]
            calibrated = self._sigmoid(
                float(calibration["platt_a"]) * self._logit(raw)
                + float(calibration["platt_b"])
            )
            probabilities[target] = {
                "raw": raw,
                "calibrated": calibrated,
                "base_rate_pct": float(calibration["base_rate%"]),
                "oos_hit_pct": float(calibration["oos_hit%"]),
                "oos_auc": float(calibration.get("oos_auc", 0.0)),
                "oos_n": int(calibration.get("n", 0)),
            }
        return probabilities

    @staticmethod
    def _sigmoid(value: float) -> float:
        value = max(-35.0, min(35.0, float(value)))
        return 1.0 / (1.0 + math.exp(-value))

    @staticmethod
    def _logit(probability: float) -> float:
        probability = min(max(float(probability), 1e-4), 1.0 - 1e-4)
        return math.log(probability / (1.0 - probability))

    def _matched_scenarios(self, inputs: dict[str, Any]) -> list[dict[str, Any]]:
        flags = {
            "panic_washout": inputs["dd252"] <= -10 and inputs["india_vix"] > 20,
            "both_panic": inputs["india_vix_pct"] > 70 and inputs["us_vix_pct"] > 70,
            "slow_bleed": inputs["rsi14"] < 30 and inputs["india_vix"] < 17,
            "deep_oversold_fear": (
                inputs["dist200"] < -5
                and inputs["rsi14"] < 30
                and inputs["india_vix_pct"] > 50
            ),
            "retest": -1 <= inputs["dist6mlow"] <= 3 and inputs["rsi14"] < 40,
            "local_fear": inputs["india_vix_pct"] > 50 and inputs["us_vix_pct"] < 50,
            "momentum_bull": inputs["dist200"] > 0 and inputs["bull_count"] >= 4,
            "complacency": (
                inputs["india_vix_pct"] < 25
                and inputs["us_vix_pct"] < 30
                and inputs["rsi14"] > 65
            ),
        }
        scenarios = self.model_data["scenarios"]
        result = []
        for key in self.model_data["scenario_order"]:
            if not flags.get(key) or key not in scenarios:
                continue
            definition = scenarios[key]
            stats = definition.get("stats_all", {})
            ret3 = stats.get("ret3", {})
            if int(ret3.get("n", 0)) < 5:
                continue
            result.append({
                "key": key,
                "name": definition.get("name", key),
                "rule": definition.get("rule", ""),
                "meaning": definition.get("meaning", ""),
                "historical_action": definition.get("action", ""),
                "events": int(stats.get("events", ret3.get("n", 0))),
                "one_month": stats.get("ret1", {}),
                "three_month": ret3,
                "typical_dip_3m_pct": stats.get("dip3"),
                "typical_rally_3m_pct": stats.get("rally3"),
            })
        return result

    def _scenario_composite(self, matched: list[dict[str, Any]], nifty: float) -> dict[str, Any]:
        eligible = [
            row for row in matched
            if int(row.get("three_month", {}).get("n", 0)) >= 5
        ]
        bucket_medians = self.model_data.get("model_bucket_medians_pct", {"1M": 1.6, "3M": 4.2})
        model_1m = float(bucket_medians["1M"])
        model_3m = float(bucket_medians["3M"])
        if eligible:
            scenario_1m = sum(float(row["one_month"]["med"]) for row in eligible) / len(eligible)
            scenario_3m = sum(float(row["three_month"]["med"]) for row in eligible) / len(eligible)
            one_month_pct = 0.5 * scenario_1m + 0.5 * model_1m
            three_month_pct = 0.5 * scenario_3m + 0.5 * model_3m
            dip_values = [float(row["typical_dip_3m_pct"]) for row in eligible if row.get("typical_dip_3m_pct") is not None]
            rally_values = [float(row["typical_rally_3m_pct"]) for row in eligible if row.get("typical_rally_3m_pct") is not None]
            typical_dip = sum(dip_values) / len(dip_values) if dip_values else None
            typical_rally = sum(rally_values) / len(rally_values) if rally_values else None
        else:
            one_month_pct, three_month_pct = model_1m, model_3m
            typical_dip = typical_rally = None

        return {
            "one_month_median_pct": one_month_pct,
            "one_month_level": nifty * (1.0 + one_month_pct / 100.0),
            "three_month_median_pct": three_month_pct,
            "three_month_level": nifty * (1.0 + three_month_pct / 100.0),
            "typical_dip_3m_pct": typical_dip,
            "typical_dip_level": nifty * (1.0 + typical_dip / 100.0) if typical_dip is not None else None,
            "typical_rally_3m_pct": typical_rally,
            "typical_rally_level": nifty * (1.0 + typical_rally / 100.0) if typical_rally is not None else None,
            "matched_scenario_count": len(eligible),
            "estimate_method": (
                "50% matched-scenario median + 50% supplied model-bucket median"
                if eligible else "supplied model-bucket median (no matched scenario available)"
            ),
        }

    def predict_from_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Apply the supplied frozen model to already-computed current features."""
        probabilities = self._predict_probabilities(inputs)
        raw3 = probabilities["y_up_3M"]["raw"]
        bucket_index = sum(raw3 > float(cutoff) for cutoff in self.model_data["quintile_cutoffs"])
        bucket = dict(self.model_data["quintiles"][bucket_index])
        bucket["raw_probability"] = raw3
        matched = self._matched_scenarios(inputs)
        composite = self._scenario_composite(matched, float(inputs["nifty"]))
        return {
            "available": True,
            "as_of": inputs.get("as_of"),
            "model_snapshot_as_of": self.model_data.get("meta", {}).get("as_of"),
            "inputs": inputs,
            "probabilities": probabilities,
            "confidence_bucket": bucket,
            "matched_scenarios": matched,
            "composite": composite,
            "accuracy": self.model_data.get("accuracy", {}),
        }

    def run(self, history: pd.DataFrame | None = None) -> dict[str, Any]:
        """Fetch current data and return a report-ready forecast.

        Network/data-quality failures are returned as an unavailable status. The daily
        institutional report can still complete, and importantly no frozen old forecast
        is presented as if it were live.
        """
        try:
            prices = history if history is not None else self._fetch_history()
            inputs = self.build_inputs(prices)
            return self.predict_from_inputs(inputs)
        except Exception as exc:  # Keep an auxiliary overlay from blocking the core report.
            return {
                "available": False,
                "error": f"{type(exc).__name__}: {exc}",
                "model_snapshot_as_of": self.model_data.get("meta", {}).get("as_of"),
            }


if __name__ == "__main__":
    result = NiftyScenarioEngine().run()
    if not result.get("available"):
        print("NIFTY scenario overlay unavailable:", result.get("error", "unknown error"))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
