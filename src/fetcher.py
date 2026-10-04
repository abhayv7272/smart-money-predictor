"""Free-data fetchers for NSE participant OI and Yahoo Finance market history."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import random
import sqlite3
from decimal import Decimal, InvalidOperation
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from index_universe import INDEX_UNIVERSE, symbols_for_history
from market_data import MarketDataError, download_yahoo, history_is_fresh
from nse_calendar import is_nse_equity_trading_day, latest_completed_nse_session


OI_FIELDS = (
    "future_index_long", "future_index_short", "future_stock_long", "future_stock_short",
    "option_index_call_long", "option_index_put_long", "option_index_call_short", "option_index_put_short",
    "option_stock_call_long", "option_stock_put_long", "option_stock_call_short", "option_stock_put_short",
    "total_long_contracts", "total_short_contracts",
)
OI_PARTICIPANTS = {"Client", "DII", "FII", "Pro"}
OI_ALLOWED_TYPES = OI_PARTICIPANTS | {"TOTAL"}
OI_HISTORY_MAX_GAP_DAYS = 10

# These values are actual comparable Yahoo indices/benchmarks. Do not substitute ETFs
# with a different numerical scale (e.g. SPY for the S&P 500 index or UUP for DXY).
MACRO_TICKERS = {
    "brent_crude": "BZ=F",
    "us_10y_yield": "^TNX",
    "us_dollar_index": "DX-Y.NYB",
    "dow_jones": "^DJI",
    "sp500": "^GSPC",
    "nifty_50": "^NSEI",
    "bank_nifty": "^NSEBANK",
}

# Match participant-OI fields by normalized header labels only. A positional fallback
# is unsafe: a changed archive layout could silently swap long/short or call/put values.
_HEADER_ALIASES = {
    "futureindexlong": "future_index_long",
    "futuresindexlong": "future_index_long",
    "futureindexshort": "future_index_short",
    "futuresindexshort": "future_index_short",
    "futurestocklong": "future_stock_long",
    "futuresstocklong": "future_stock_long",
    "futurestockshort": "future_stock_short",
    "futuresstockshort": "future_stock_short",
    "optionindexcalllong": "option_index_call_long",
    "optionindexputlong": "option_index_put_long",
    "optionindexcallshort": "option_index_call_short",
    "optionindexputshort": "option_index_put_short",
    "optionstockcalllong": "option_stock_call_long",
    "optionstockputlong": "option_stock_put_long",
    "optionstockcallshort": "option_stock_call_short",
    "optionstockputshort": "option_stock_put_short",
    "totallongcontracts": "total_long_contracts",
    "totalshortcontracts": "total_short_contracts",
}


class StaleParticipantDataError(ValueError):
    """Raised rather than calculating current signals from an old OI cache."""


class FreeDataFetcher:
    def __init__(self, config_path="config.json", db_path="data/participant_oi_master.db",
                 http_session=None, yahoo_downloader=None):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = config_path if os.path.isabs(config_path) else os.path.join(self.base_dir, config_path)
        self.db_path = db_path if os.path.isabs(db_path) else os.path.join(self.base_dir, db_path)
        self.yahoo_downloader = yahoo_downloader
        self.http_session = http_session
        self.last_sector_diagnostics = {
            "total_indices": 0,
            "scanned_indices": 0,
            "failed_indices": [],
            "errors": [],
            "status": "not_run",
        }

        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as handle:
                self.config = json.load(handle)
            if not isinstance(self.config, dict):
                raise ValueError("config.json must contain a JSON object.")
        else:
            self.config = {"recipient_email": "", "sectors": [], "macro_tickers": {}}

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

    def _get_headers(self):
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/csv,text/plain,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    @staticmethod
    def _coerce_date(value=None):
        if value is None:
            return dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        parsed = pd.to_datetime(value, errors="raise")
        return parsed.date()

    @staticmethod
    def _normalize_header(value):
        return "".join(ch.casefold() for ch in str(value).strip() if ch.isalnum())

    @staticmethod
    def _parse_contract_count(value):
        text = str(value).strip().replace(",", "").replace('"', "")
        if not text:
            raise ValueError("empty contract count")
        number = Decimal(text)
        if not number.is_finite() or number != number.to_integral_value() or number < 0:
            raise ValueError("contract count must be a non-negative integer")
        return int(number)

    @classmethod
    def _validate_oi_records(cls, records, expected_date=None):
        """Return normalized rows only when all four participant types are unique/complete."""
        if not records:
            raise ValueError("participant OI response contains no records")
        normalized = []
        seen = set()
        dates = set()
        for source in records:
            row = dict(source)
            row_date = pd.to_datetime(row.get("date"), errors="coerce")
            if pd.isna(row_date):
                raise ValueError("participant OI row has an invalid date")
            date_str = row_date.date().isoformat()
            dates.add(date_str)
            participant = str(row.get("client_type", "")).strip()
            if participant not in OI_ALLOWED_TYPES:
                raise ValueError(f"unexpected participant type {participant!r}")
            key = (date_str, participant)
            if key in seen:
                raise ValueError(f"duplicate {participant} participant row for {date_str}")
            seen.add(key)
            if not set(OI_FIELDS).issubset(row):
                raise ValueError(f"participant OI row for {participant} is missing fields")
            row["date"] = date_str
            row["client_type"] = participant
            for field in OI_FIELDS:
                row[field] = cls._parse_contract_count(row[field])
            normalized.append(row)

        if len(dates) != 1:
            raise ValueError("participant OI response mixes dates")
        only_date = next(iter(dates))
        if expected_date is not None and only_date != cls._coerce_date(expected_date).isoformat():
            raise ValueError(f"participant OI date mismatch: expected {expected_date}, got {only_date}")
        participants = [r["client_type"] for r in normalized if r["client_type"] in OI_PARTICIPANTS]
        if set(participants) != OI_PARTICIPANTS or len(participants) != len(OI_PARTICIPANTS):
            raise ValueError("participant OI response must contain exactly one Client, DII, FII and Pro row")
        if sum(r["client_type"] == "TOTAL" for r in normalized) > 1:
            raise ValueError("participant OI response contains duplicate TOTAL rows")
        return normalized

    def fetch_latest_participant_oi(self, target_date=None, max_business_days=5, max_age_days=7):
        """Fetch official NSE OI, otherwise use only a complete and recent SQLite snapshot.

        Weekends and known NSE equity holidays are skipped, each request has a bounded
        connect/read timeout, and the fallback is rejected if it is stale. No
        incomplete/duplicate participant table can flow into the calculator.
        """
        if target_date is None:
            # Do not request today's archive before the NSE session has completed.
            # Keep staleness measured against today's calendar date, not the session date.
            reference_date = self._coerce_date()
            cur_date = latest_completed_nse_session()
        else:
            cur_date = self._coerce_date(target_date)
            reference_date = cur_date
        print(f"[INFO] Scanning official NSE Participant OI from: {cur_date}")
        owns_session = self.http_session is None
        session = self.http_session or requests.Session()
        checked = 0
        try:
            offset = 0
            while checked < max(1, int(max_business_days)) and offset < 30:
                current = cur_date - dt.timedelta(days=offset)
                offset += 1
                if not is_nse_equity_trading_day(current):
                    continue
                checked += 1
                date_token = current.strftime("%d%m%Y")
                url = f"https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{date_token}.csv"
                try:
                    response = session.get(url, headers=self._get_headers(), timeout=(3.05, 7))
                    if response.status_code != 200:
                        print(f"[WARN] NSE archive {current}: HTTP {response.status_code}")
                        continue
                    text = response.content.decode("utf-8-sig", errors="replace")
                    records = self._parse_participant_csv(text, current.isoformat())
                    records = self._validate_oi_records(records or [], expected_date=current)
                    self._save_to_db(records)
                    age_days = (reference_date - current).days
                    result = {
                        "date": current.isoformat(),
                        "display_date": current.strftime("%d %B %Y"),
                        "raw_data": records,
                        "status": "success",
                        "data_status": "live",
                        "source": "live_nse_exchange",
                        "age_days": age_days,
                        "url": url,
                    }
                    print(f"[SUCCESS] Official NSE OI {current.isoformat()} ({len(records)} rows)")
                    return result
                except requests.RequestException as exc:
                    detail = str(exc).splitlines()[0] if str(exc) else "no HTTP response received"
                    print(
                        f"[WARN] NSE archive {current}: request failed ({type(exc).__name__}: {detail}); "
                        "archive availability could not be confirmed."
                    )
                except ValueError as exc:
                    # A bad/non-CSV response is not a valid market-data snapshot.
                    print(f"[WARN] NSE archive {current}: invalid response ({exc})")
        finally:
            if owns_session:
                session.close()

        print("[WARNING] No valid NSE archive response; checking recent validated SQLite cache instead.")
        return self._get_latest_from_db(reference_date=reference_date, max_age_days=max_age_days)

    def _parse_participant_csv(self, content, date_str):
        """Parse the NSE CSV by field name (with a strict legacy-order fallback)."""
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(StringIO(str(content))))
        header_index = next(
            (i for i, row in enumerate(rows[:15])
             if row and self._normalize_header(row[0]).lstrip("\ufeff") == "clienttype"),
            None,
        )
        if header_index is None:
            return None
        header = rows[header_index]
        positions = {}
        for index, label in enumerate(header[1:15], start=1):
            mapped = _HEADER_ALIASES.get(self._normalize_header(label))
            if mapped:
                positions[mapped] = index
        if len(positions) != len(OI_FIELDS):
            # A changed/unrecognized header is not safe to interpret positionally; doing so
            # could silently swap long/short or call/put exposures.
            return None

        records = []
        seen = set()
        for line_number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            if not row or not row[0].strip():
                continue
            participant = row[0].strip()
            if participant not in OI_ALLOWED_TYPES:
                continue
            if participant in seen:
                raise ValueError(f"duplicate {participant} row on CSV line {line_number}")
            if len(row) <= max(positions.values()):
                raise ValueError(f"short {participant} row on CSV line {line_number}")
            try:
                values = {field: self._parse_contract_count(row[column]) for field, column in positions.items()}
            except (ValueError, InvalidOperation) as exc:
                raise ValueError(f"invalid numeric value in {participant} row on CSV line {line_number}") from exc
            record = {"date": self._coerce_date(date_str).isoformat(), "client_type": participant}
            record.update(values)
            records.append(record)
            seen.add(participant)
        if set(r["client_type"] for r in records if r["client_type"] in OI_PARTICIPANTS) != OI_PARTICIPANTS:
            return None
        return self._validate_oi_records(records, expected_date=date_str)

    def _save_to_db(self, records):
        if not records:
            return False
        try:
            clean = self._validate_oi_records(records, expected_date=records[0]["date"])
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=15) as conn:
                table_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='participant_oi_raw'"
                ).fetchone()
                if table_exists:
                    columns = {row[1] for row in conn.execute("PRAGMA table_info(participant_oi_raw)")}
                    required = {"date", "client_type", *OI_FIELDS}
                    if not required.issubset(columns):
                        raise ValueError("participant_oi_raw schema is missing required columns")
                    conn.execute("DELETE FROM participant_oi_raw WHERE date = ?", (clean[0]["date"],))
                pd.DataFrame(clean).to_sql("participant_oi_raw", conn, if_exists="append", index=False)
            return True
        except Exception as exc:
            print(f"[DB_ERROR] Failed to cache participant OI: {type(exc).__name__}: {exc}")
            return False

    def _get_latest_from_db(self, reference_date=None, max_age_days=7):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database {self.db_path} not found.")
        reference_date = self._coerce_date(reference_date)
        with sqlite3.connect(self.db_path, timeout=15) as conn:
            schema = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='participant_oi_raw'"
            ).fetchone()
            if not schema:
                raise ValueError("participant_oi_raw table is missing from the OI database")
            latest = conn.execute(
                "SELECT date FROM participant_oi_raw WHERE date <= ? ORDER BY date DESC LIMIT 1",
                (reference_date.isoformat(),),
            ).fetchone()
            if not latest:
                raise ValueError("No participant data found in database on or before the requested date")
            latest_date = self._coerce_date(latest[0])
            df = pd.read_sql_query(
                "SELECT * FROM participant_oi_raw WHERE date = ? ORDER BY client_type",
                conn,
                params=(latest_date.isoformat(),),
            )
        records = self._validate_oi_records(df.to_dict(orient="records"), expected_date=latest_date)
        age_days = (reference_date - latest_date).days
        if age_days < 0 or age_days > int(max_age_days):
            raise StaleParticipantDataError(
                f"Latest participant OI cache is {age_days} days old ({latest_date}); "
                f"maximum allowed is {max_age_days} days. Refusing to calculate a current signal."
            )
        return {
            "date": latest_date.isoformat(),
            "display_date": latest_date.strftime("%d %B %Y"),
            "raw_data": records,
            "status": "success",
            "data_status": "cached",
            "source": "sqlite_cache",
            "age_days": age_days,
        }

    def fetch_recent_history(self, days_count=15, max_calendar_gap_days=OI_HISTORY_MAX_GAP_DAYS, max_latest_age_days=7):
        """Fetch complete consecutive-enough OI dates; never compute changes over data gaps."""
        try:
            days_count = int(days_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("days_count must be an integer") from exc
        if not 3 <= days_count <= 1000:
            raise ValueError("days_count must be between 3 and 1000")
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database {self.db_path} not found.")

        with sqlite3.connect(self.db_path, timeout=15) as conn:
            dates = [row[0] for row in conn.execute(
                "SELECT DISTINCT date FROM participant_oi_raw ORDER BY date DESC LIMIT ?",
                (days_count,),
            )]
            if not dates:
                raise ValueError("No participant OI history is available in SQLite")
            newest_first = [self._coerce_date(value) for value in dates]
            continuous_dates = [newest_first[0]]
            for older in newest_first[1:]:
                newer = continuous_dates[-1]
                gap_days = (newer - older).days
                if gap_days > int(max_calendar_gap_days):
                    print(
                        f"[WARN] OI history discontinuity: {older.isoformat()} -> {newer.isoformat()} "
                        f"({gap_days} calendar days). Ignoring older dates."
                    )
                    break
                continuous_dates.append(older)
            selected_dates = [value.isoformat() for value in continuous_dates]
            placeholders = ",".join("?" for _ in selected_dates)
            df = pd.read_sql_query(
                f"SELECT * FROM participant_oi_raw WHERE date IN ({placeholders}) ORDER BY date ASC, client_type ASC",
                conn,
                params=selected_dates,
            )

        normalized_dates = sorted(continuous_dates)
        reference_date = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        latest_age = (reference_date - normalized_dates[-1]).days
        if latest_age < 0 or latest_age > int(max_latest_age_days):
            raise StaleParticipantDataError(
                f"Recent OI history ends {latest_age} days ago ({normalized_dates[-1]}); "
                f"maximum allowed is {max_latest_age_days} days."
            )
        if len(normalized_dates) < 3:
            latest_completed = latest_completed_nse_session()
            if reference_date > latest_completed and is_nse_equity_trading_day(reference_date):
                timing_note = (
                    f" The {reference_date.isoformat()} NSE session has not closed yet; its OI archive is "
                    "normally expected only after the 15:30 IST close. Rerun after the close/archive publication."
                )
            else:
                timing_note = (
                    f" The latest completed NSE session is {latest_completed.isoformat()}; "
                    "retry when that session's official OI archive is reachable."
                )
            raise ValueError(
                f"Need at least 3 recent, continuous participant OI dates; found {len(normalized_dates)} "
                "before the next large history gap. Do not mix older snapshots across that gap."
                + timing_note
            )
        for date_value, group in df.groupby("date", sort=True):
            self._validate_oi_records(group.to_dict(orient="records"), expected_date=date_value)
        return df

    def _fetch_close_history(self, symbol, period="7d", max_age_days=10):
        history = download_yahoo(
            symbol,
            period=period,
            interval="1d",
            timeout=8,
            attempts=1,
            downloader=self.yahoo_downloader,
        )
        if not history_is_fresh(history, max_age_days=max_age_days,
                                reference_date=dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()):
            raise MarketDataError(f"Yahoo Finance {symbol} history is stale or future-dated.")
        return history

    def fetch_global_macro(self):
        """Fetch current macro/index values with timeout, freshness and correct units.

        Missing feeds are represented by `current=None` and status=`unavailable`; zero is
        never used as a fake neutral reading. Yahoo's ^TNX is quoted in tenths of a percent,
        so its displayed 10-year yield is scaled down by 10.
        """
        results = {}
        configured = self.config.get("macro_tickers", {})
        for key, default_symbol in MACRO_TICKERS.items():
            symbol = configured.get(key, default_symbol) if isinstance(configured, dict) else default_symbol
            entry = {
                "symbol": symbol,
                "source": "Yahoo Finance",
                "current": None,
                "previous": None,
                "change_pct": None,
                "as_of": None,
                "status": "unavailable",
                "error": None,
            }
            try:
                history = self._fetch_close_history(symbol, period="7d", max_age_days=10)
                closes = history["Close"].dropna()
                if closes.empty:
                    raise MarketDataError(f"Yahoo Finance {symbol} has no valid close")
                current_raw = float(closes.iloc[-1])
                previous_raw = float(closes.iloc[-2]) if len(closes) > 1 else None
                # CBOE 10Y (^TNX) encodes percent x 10 (e.g. 43.5 means 4.35%).
                scale = 0.1 if key == "us_10y_yield" and symbol == "^TNX" else 1.0
                current = current_raw * scale
                previous = previous_raw * scale if previous_raw is not None else None
                change_pct = ((current / previous) - 1) * 100 if previous and previous > 0 else None
                entry.update({
                    "current": round(current, 4 if key == "us_10y_yield" else 2),
                    "previous": round(previous, 4 if key == "us_10y_yield" else 2) if previous is not None else None,
                    "change_pct": round(change_pct, 2) if change_pct is not None else None,
                    "as_of": pd.Timestamp(history.index[-1]).date().isoformat(),
                    "status": "ok",
                    "error": None,
                })
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                print(f"[WARN] Macro feed {key} ({symbol}) unavailable: {entry['error']}")
            results[key] = entry
        return results

    def fetch_sector_strength(self):
        """Calculate fresh sector RS and retain coverage/errors for report diagnostics.

        The public result remains the historical list API; callers can read the detailed
        per-index outcome from `last_sector_diagnostics` without treating missing feeds as
        neutral or as a full-universe no-leader result.
        """
        reference_date = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        selected = [
            item for item in INDEX_UNIVERSE
            if item["category"] == "Sectoral" or item["name"] in {"Nifty Midcap 50", "Nifty Smallcap 250"}
        ]
        errors = []

        def history(item):
            attempts = []
            for symbol in symbols_for_history(item):
                try:
                    data = download_yahoo(
                        symbol, period="3mo", interval="1d", timeout=8, attempts=1,
                        require_ohlc=True, downloader=self.yahoo_downloader,
                    )
                    if len(data) < 22:
                        raise MarketDataError(f"only {len(data)} valid daily bars; 22 required")
                    if not history_is_fresh(data, max_age_days=7, reference_date=reference_date):
                        raise MarketDataError("latest daily bar is stale or future-dated")
                    return data, symbol
                except Exception as exc:
                    attempts.append(f"{symbol}: {type(exc).__name__}: {exc}")
            if not attempts:
                attempts.append("no actual-index or index-tracking ETF history symbol configured")
            failure = {"name": item["name"], "reason": "; ".join(attempts)}
            errors.append(failure)
            print(f"[WARN] Sector history unavailable for {item['name']}: {failure['reason']}")
            return pd.DataFrame(), None

        benchmark = next((item for item in INDEX_UNIVERSE if item["name"] == "Nifty 50"), None)
        if benchmark is None:
            errors.append({"name": "Nifty 50 (benchmark)", "reason": "benchmark definition is missing"})
            self.last_sector_diagnostics = {
                "total_indices": len(selected),
                "scanned_indices": 0,
                "failed_indices": [item["name"] for item in selected],
                "errors": errors,
                "benchmark_available": False,
                "status": "unavailable",
            }
            return []

        bench_history, bench_symbol = history(benchmark)
        if len(bench_history) < 22:
            print("[WARN] Nifty benchmark unavailable; sector RS cannot be computed safely.")
            self.last_sector_diagnostics = {
                "total_indices": len(selected),
                "scanned_indices": 0,
                "failed_indices": [item["name"] for item in selected],
                "errors": errors,
                "benchmark_available": False,
                "status": "unavailable",
            }
            return []

        bench_close = bench_history["Close"]
        benchmark_1w = float((bench_close.iloc[-1] / bench_close.iloc[-5] - 1) * 100)
        benchmark_1m = float((bench_close.iloc[-1] / bench_close.iloc[-22] - 1) * 100)
        result = []
        for item in selected:
            data, symbol = history(item)
            if len(data) < 22:
                continue
            close = data["Close"]
            current = float(close.iloc[-1])
            day_change = float((current / close.iloc[-2] - 1) * 100)
            week_change = float((current / close.iloc[-5] - 1) * 100)
            month_change = float((current / close.iloc[-22] - 1) * 100)
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            above_ema = current >= ema20 * 0.995
            # Match the documented blend: 60% relative 1-week momentum, 40% 1-month.
            relative_score = round(
                0.6 * (week_change - benchmark_1w) + 0.4 * (month_change - benchmark_1m), 2
            )
            if relative_score > 2 and above_ema:
                status, code = "LEADER (Strong Outperformance)", "LEADER"
            elif relative_score > 0:
                status, code = "IMPROVING (Outperforming)", "IMPROVING"
            elif relative_score > -2.5:
                status, code = "NEUTRAL (In Line)", "NEUTRAL"
            else:
                status, code = "LAGGARD (Underperforming)", "LAGGARD"
            result.append({
                "name": item["name"],
                "ticker": symbol,
                "data_source": "actual_index" if symbol == item.get("index_symbol") else "index_tracking_etf",
                "benchmark_ticker": bench_symbol,
                "description": item["description"],
                "current": round(current, 2),
                "chg_1d": round(day_change, 2),
                "chg_1w": round(week_change, 2),
                "chg_1m": round(month_change, 2),
                "above_20_ema": bool(above_ema),
                "rs_score": relative_score,
                "status": status,
                "status_code": code,
                "as_of": data.index[-1].date().isoformat(),
            })

        failed_names = [error["name"] for error in errors if error["name"] in {item["name"] for item in selected}]
        self.last_sector_diagnostics = {
            "total_indices": len(selected),
            "scanned_indices": len(result),
            "failed_indices": failed_names,
            "errors": errors,
            "benchmark_available": True,
            "benchmark_ticker": bench_symbol,
            "status": "unavailable" if not result else "partial" if failed_names else "ok",
        }
        return sorted(result, key=lambda row: row["rs_score"], reverse=True)
