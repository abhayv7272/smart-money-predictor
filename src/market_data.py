"""Shared, defensive Yahoo Finance data helpers.

Yahoo's pandas column/index shape has changed several times (notably single-ticker
MultiIndex columns). Keep all consumers on one canonical OHLCV representation and
reject invalid/stale bars instead of silently treating an empty feed as no signal.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from typing import Callable

import pandas as pd


class MarketDataError(RuntimeError):
    """Raised when a requested Yahoo Finance history is absent or invalid."""


_FIELD_NAMES = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "adj close": "Adj Close",
    "adjusted close": "Adj Close",
    "volume": "Volume",
}
_OHLC = ("Open", "High", "Low", "Close")
_OUTPUT_ORDER = ("Open", "High", "Low", "Close", "Adj Close", "Volume")
_MEMORY_CACHE: dict[tuple, pd.DataFrame] = {}


def clear_market_data_cache() -> None:
    """Clear the process-local response cache (primarily for isolated tests)."""
    _MEMORY_CACHE.clear()


def _field_name(label) -> str | None:
    return _FIELD_NAMES.get(str(label).strip().casefold())


def normalize_yahoo_frame(
    frame: pd.DataFrame | None,
    *,
    symbol: str | None = None,
    interval: str = "1d",
    intraday_timezone: str | None = None,
    require_ohlc: bool = False,
) -> pd.DataFrame:
    """Convert a Yahoo response into sorted, validated, flat columns.

    Supports both `(Price, Ticker)` and `(Ticker, Price)` MultiIndex layouts. For
    daily bars, exchange-local date labels are preserved when removing time zones;
    intraday consumers may request an explicit timezone conversion before removal.
    """
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()

    source = frame.copy()
    selected: dict[str, pd.Series] = {}

    if isinstance(source.columns, pd.MultiIndex):
        columns = list(source.columns)
        known_symbols = {str(part) for col in columns for part in (col if isinstance(col, tuple) else (col,))
                         if _field_name(part) is None}
        if symbol and symbol in known_symbols:
            selected_columns = [
                col for col in columns
                if symbol in tuple(str(part) for part in (col if isinstance(col, tuple) else (col,)))
            ]
        elif len(known_symbols) <= 1:
            # Single-symbol responses can use Yahoo's normalized ticker label.
            selected_columns = columns
        else:
            return pd.DataFrame()

        for column in selected_columns:
            parts = column if isinstance(column, tuple) else (column,)
            field = next((_field_name(part) for part in parts if _field_name(part)), None)
            if field is None:
                continue
            # Prefer the unadjusted Close over Adj Close if columns collapse to one field.
            series = source[column]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[:, 0]
            if field not in selected or (field == "Close" and str(column).casefold().find("adj") >= 0):
                selected[field] = series
    else:
        for column in source.columns:
            field = _field_name(column)
            if field is None:
                continue
            series = source[column]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[:, 0]
            if field not in selected:
                selected[field] = series

    if not selected:
        return pd.DataFrame()

    result = pd.DataFrame(selected, index=source.index)
    if "Close" not in result.columns and "Adj Close" in result.columns:
        result["Close"] = result["Adj Close"]
    parsed_index = pd.DatetimeIndex(pd.to_datetime(result.index, errors="coerce"))
    valid_index = ~parsed_index.isna()
    result = result.loc[valid_index].copy()
    parsed_index = parsed_index[valid_index]
    if parsed_index.tz is not None:
        if intraday_timezone:
            parsed_index = parsed_index.tz_convert(intraday_timezone).tz_localize(None)
        else:
            # Preserve the source exchange's local calendar date for cross-market joins.
            parsed_index = parsed_index.tz_localize(None)
    if interval in {"1d", "1D", "day", "daily"}:
        parsed_index = parsed_index.normalize()
    result.index = parsed_index
    result = result[~result.index.duplicated(keep="last")].sort_index()

    for column in result.columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.replace([float("inf"), float("-inf")], pd.NA)

    if require_ohlc:
        if not set(_OHLC).issubset(result.columns):
            return pd.DataFrame()
        values = result.loc[:, _OHLC]
        finite_positive = values.notna().all(axis=1) & (values > 0).all(axis=1)
        geometry_ok = (
            (result["High"] >= result["Low"])
            & (result["High"] >= result[["Open", "Close"]].max(axis=1))
            & (result["Low"] <= result[["Open", "Close"]].min(axis=1))
        )
        result = result.loc[finite_positive & geometry_ok].copy()
    elif "Close" in result.columns:
        result = result.loc[result["Close"].notna() & (result["Close"] > 0)].copy()

    # A number of index feeds omit Volume; volume is unused by the sweep scoring.
    if "Volume" not in result.columns and set(_OHLC).issubset(result.columns):
        result["Volume"] = 0.0
    ordered = [column for column in _OUTPUT_ORDER if column in result.columns]
    return result.loc[:, ordered]


def history_is_fresh(
    frame: pd.DataFrame,
    *,
    max_age_days: int = 7,
    reference_date: date | None = None,
) -> bool:
    """Return whether the latest bar is recent enough for an EOD Indian-market run."""
    if frame is None or frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return False
    latest_date = pd.Timestamp(frame.index[-1]).date()
    today = reference_date or datetime.now().date()
    age = (today - latest_date).days
    return 0 <= age <= max_age_days


def download_yahoo(
    symbol: str,
    *,
    period: str = "1y",
    interval: str = "1d",
    start: str | None = None,
    timeout: int = 10,
    attempts: int = 1,
    intraday_timezone: str | None = None,
    require_ohlc: bool = False,
    downloader: Callable | None = None,
) -> pd.DataFrame:
    """Download and validate one ticker with a bounded timeout/retry count.

    `downloader` is injectable for deterministic tests. Errors are normalized into
    MarketDataError so individual scanners can record the failing ticker and continue.
    """
    if not symbol or not isinstance(symbol, str):
        raise MarketDataError("A non-empty Yahoo Finance ticker is required.")
    attempts = max(1, min(int(attempts), 3))
    use_cache = downloader is None
    cache_key = (symbol, start or period, interval, intraday_timezone, require_ohlc)
    if use_cache and cache_key in _MEMORY_CACHE:
        return _MEMORY_CACHE[cache_key].copy()
    if downloader is None:
        import yfinance as yf
        downloader = yf.download

    last_error = "no rows returned"
    for attempt in range(attempts):
        try:
            kwargs = {
                "interval": interval,
                "progress": False,
                "auto_adjust": False,
                "timeout": timeout,
                "threads": False,
            }
            if start:
                kwargs["start"] = start
            else:
                kwargs["period"] = period
            raw = downloader(symbol, **kwargs)
            result = normalize_yahoo_frame(
                raw,
                symbol=symbol,
                interval=interval,
                intraday_timezone=intraday_timezone,
                require_ohlc=require_ohlc,
            )
            if not result.empty:
                if use_cache:
                    if len(_MEMORY_CACHE) >= 128:
                        _MEMORY_CACHE.pop(next(iter(_MEMORY_CACHE)))
                    _MEMORY_CACHE[cache_key] = result.copy()
                return result.copy()
            last_error = "empty response or no valid Close/OHLC bars"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt + 1 < attempts:
            time.sleep(0.25 * (attempt + 1))

    raise MarketDataError(f"Yahoo Finance {symbol} unavailable ({last_error[:220]}).")
