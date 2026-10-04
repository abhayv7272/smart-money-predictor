import datetime as dt
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fetcher as fetcher_module
from calculator import InstitutionalCalculator
from fetcher import FreeDataFetcher, OI_FIELDS, StaleParticipantDataError
from market_data import MarketDataError, download_yahoo, normalize_yahoo_frame
from nse_calendar import is_nse_equity_trading_day, latest_completed_nse_session


PARTICIPANTS = ("Client", "DII", "FII", "Pro")


def make_oi_records(date_value, fii_stock_net=1000):
    rows = []
    for index, participant in enumerate(PARTICIPANTS):
        row = {"date": str(date_value), "client_type": participant}
        row.update({field: 0 for field in OI_FIELDS})
        row["future_index_long"] = 60 if participant == "FII" else 10 + index
        row["future_index_short"] = 40 if participant == "FII" else 5 + index
        row["future_stock_long"] = fii_stock_net + 5000 if participant == "FII" else 100 + index
        row["future_stock_short"] = 5000 if participant == "FII" else 50 + index
        row["total_long_contracts"] = sum(row[field] for field in OI_FIELDS[:12:2])
        row["total_short_contracts"] = sum(row[field] for field in OI_FIELDS[1:12:2])
        rows.append(row)
    return rows


def yahoo_multiindex(symbol, close_values, orientation="price_first", index=None):
    index = index if index is not None else pd.bdate_range(end=dt.datetime.now(ZoneInfo("Asia/Kolkata")).date(), periods=len(close_values))
    closes = np.asarray(close_values, dtype=float)
    values = {
        "Open": closes,
        "High": closes + 1,
        "Low": closes - 1,
        "Close": closes,
        "Volume": np.full(len(closes), 1000.0),
    }
    if orientation == "price_first":
        columns = pd.MultiIndex.from_tuples([(field, symbol) for field in values])
    else:
        columns = pd.MultiIndex.from_tuples([(symbol, field) for field in values])
    return pd.DataFrame(np.column_stack(list(values.values())), index=index, columns=columns)


class YahooNormalizerTests(unittest.TestCase):
    def test_normalizes_both_multiindex_level_orders(self):
        for orientation in ("price_first", "ticker_first"):
            with self.subTest(orientation=orientation):
                raw = yahoo_multiindex("^NSEI", [100, 101, 102], orientation)
                normalized = normalize_yahoo_frame(raw, symbol="^NSEI", require_ohlc=True)
                self.assertEqual(list(normalized.columns), ["Open", "High", "Low", "Close", "Volume"])
                self.assertEqual(normalized["Close"].tolist(), [100.0, 101.0, 102.0])
                self.assertEqual(normalized.index[-1].date(), raw.index[-1].date())

    def test_invalid_ohlc_bars_are_removed_and_wrong_multi_ticker_is_rejected(self):
        idx = pd.bdate_range("2026-09-01", periods=3)
        raw = yahoo_multiindex("^NSEI", [100, 101, 102], index=idx)
        raw.loc[idx[1], ("High", "^NSEI")] = 90
        clean = normalize_yahoo_frame(raw, symbol="^NSEI", require_ohlc=True)
        self.assertEqual(len(clean), 2)
        two_tickers = pd.concat(
            [yahoo_multiindex("^NSEI", [100, 101, 102], index=idx), yahoo_multiindex("^BANK", [200, 201, 202], index=idx)],
            axis=1,
        )
        wrong_symbol = normalize_yahoo_frame(two_tickers, symbol="^VIX", require_ohlc=True)
        self.assertTrue(wrong_symbol.empty)

    def test_download_has_bounded_timeout_and_normalizes_empty_response(self):
        captured = {}

        def downloader(symbol, **kwargs):
            captured.update(kwargs)
            return yahoo_multiindex(symbol, [101, 102, 103])

        result = download_yahoo("^NSEI", timeout=6, downloader=downloader, require_ohlc=True)
        self.assertEqual(captured["timeout"], 6)
        self.assertFalse(captured["threads"])
        self.assertFalse(captured["auto_adjust"])
        self.assertEqual(float(result["Close"].iloc[-1]), 103)

        with self.assertRaises(MarketDataError):
            download_yahoo("^NSEI", downloader=lambda *_a, **_k: pd.DataFrame())


class ParticipantOITests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "oi.db")
        self.fetcher = FreeDataFetcher(
            config_path=os.path.join(self.tempdir.name, "missing-config.json"),
            db_path=self.db_path,
        )
        self.today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_csv_parser_rejects_missing_duplicate_and_malformed_participants(self):
        columns = [
            "Future Index Long", "Future Index Short", "Future Stock Long", "Future Stock Short",
            "Option Index Call Long", "Option Index Put Long", "Option Index Call Short", "Option Index Put Short",
            "Option Stock Call Long", "Option Stock Put Long", "Option Stock Call Short", "Option Stock Put Short",
            "Total Long Contracts", "Total Short Contracts",
        ]
        header = "Client Type," + ",".join(columns)
        good_rows = "".join(name + "," + ",".join(["10"] * 14) + "\n" for name in PARTICIPANTS)
        parsed = self.fetcher._parse_participant_csv(header + "\n" + good_rows, self.today)
        self.assertEqual(len(parsed), 4)
        self.assertIsNone(self.fetcher._parse_participant_csv(header + "\nClient," + ",".join(["1"] * 14), self.today))
        duplicate = header + "\n" + good_rows + "FII," + ",".join(["1"] * 14) + "\n"
        with self.assertRaisesRegex(ValueError, "duplicate FII"):
            self.fetcher._parse_participant_csv(duplicate, self.today)
        malformed = header + "\nClient," + ",".join(["1"] * 14) + "\nDII," + ",".join(["1"] * 14) + "\nFII,bad," + ",".join(["1"] * 13) + "\nPro," + ",".join(["1"] * 14)
        with self.assertRaisesRegex(ValueError, "invalid numeric"):
            self.fetcher._parse_participant_csv(malformed, self.today)

    def test_cache_requires_all_participants_and_reports_source_freshness(self):
        self.fetcher._save_to_db(make_oi_records(self.today))
        result = self.fetcher._get_latest_from_db(reference_date=self.today, max_age_days=7)
        self.assertEqual(result["source"], "sqlite_cache")
        self.assertEqual(result["data_status"], "cached")
        self.assertEqual(result["age_days"], 0)
        self.assertEqual({row["client_type"] for row in result["raw_data"]}, set(PARTICIPANTS))

        incomplete_db = os.path.join(self.tempdir.name, "incomplete.db")
        incomplete = FreeDataFetcher(config_path=os.path.join(self.tempdir.name, "none.json"), db_path=incomplete_db)
        pd.DataFrame(make_oi_records(self.today)[:-1]).to_sql("participant_oi_raw", sqlite_connect(incomplete_db), index=False)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            incomplete._get_latest_from_db(reference_date=self.today)

    def test_stale_cache_is_rejected_not_labeled_successful(self):
        old = self.today - dt.timedelta(days=30)
        self.fetcher._save_to_db(make_oi_records(old))
        with self.assertRaises(StaleParticipantDataError):
            self.fetcher._get_latest_from_db(reference_date=self.today, max_age_days=7)

    def test_recent_history_truncates_before_large_gap_and_never_uses_2024_rows(self):
        rows = []
        for offset, value in enumerate((1000, 1010, 1020)):
            day = self.today - dt.timedelta(days=offset)
            rows.extend(make_oi_records(day, 1000 + value))
        rows.extend(make_oi_records(self.today - dt.timedelta(days=730), 2000))
        pd.DataFrame(rows).to_sql("participant_oi_raw", sqlite_connect(self.db_path), index=False)
        result = self.fetcher.fetch_recent_history(days_count=10)
        self.assertEqual(result["date"].nunique(), 3)
        self.assertGreaterEqual(pd.to_datetime(result["date"].min()), pd.Timestamp(self.today - dt.timedelta(days=3)))

    def test_three_sessions_across_october_holiday_remain_a_valid_window(self):
        recent_sessions = [dt.date(2026, 10, 5), dt.date(2026, 10, 1), dt.date(2026, 9, 30)]
        rows = []
        for index, session_date in enumerate(recent_sessions):
            rows.extend(make_oi_records(session_date, 1000 + index))
        rows.extend(make_oi_records(dt.date(2024, 10, 1), 900))
        pd.DataFrame(rows).to_sql("participant_oi_raw", sqlite_connect(self.db_path), index=False)

        result = self.fetcher.fetch_recent_history(days_count=10, max_latest_age_days=10000)

        self.assertEqual(set(result["date"]), {session.isoformat() for session in recent_sessions})
        self.assertEqual(result["date"].nunique(), 3)

    def test_two_recent_sessions_before_large_gap_still_block_signal_generation(self):
        latest = latest_completed_nse_session()
        previous = latest - dt.timedelta(days=1)
        while not is_nse_equity_trading_day(previous):
            previous -= dt.timedelta(days=1)
        rows = make_oi_records(latest) + make_oi_records(previous)
        rows += make_oi_records(previous - dt.timedelta(days=730))
        pd.DataFrame(rows).to_sql("participant_oi_raw", sqlite_connect(self.db_path), index=False)

        with self.assertRaisesRegex(ValueError, "found 2 before the next large history gap"):
            self.fetcher.fetch_recent_history(days_count=10)

    def test_one_recent_session_before_large_gap_still_fails_explicitly(self):
        latest = latest_completed_nse_session()
        rows = make_oi_records(latest) + make_oi_records(latest - dt.timedelta(days=730))
        pd.DataFrame(rows).to_sql("participant_oi_raw", sqlite_connect(self.db_path), index=False)
        with self.assertRaisesRegex(ValueError, "found 1 before the next large history gap"):
            self.fetcher.fetch_recent_history(days_count=10)

    def test_nse_requests_have_timeouts_and_fallback_is_validated(self):
        self.fetcher._save_to_db(make_oi_records(self.today))
        response = Mock(status_code=404, content=b"")
        session = Mock()
        session.get.return_value = response
        self.fetcher.http_session = session
        result = self.fetcher.fetch_latest_participant_oi(target_date=self.today, max_business_days=2)
        self.assertEqual(result["source"], "sqlite_cache")
        for call in session.get.call_args_list:
            self.assertEqual(call.kwargs["timeout"], (3.05, 7))

    def test_nse_archive_search_skips_2026_october_holiday_and_weekend(self):
        reference = dt.date(2026, 10, 5)
        self.fetcher._save_to_db(make_oi_records(reference))
        session = Mock()
        session.get.return_value = Mock(status_code=404, content=b"")
        self.fetcher.http_session = session

        result = self.fetcher.fetch_latest_participant_oi(target_date=reference, max_business_days=2)

        requested_tokens = [call.args[0].rsplit("_", 1)[-1].removesuffix(".csv") for call in session.get.call_args_list]
        self.assertEqual(requested_tokens, ["05102026", "01102026"])
        self.assertEqual(result["source"], "sqlite_cache")

    def test_default_nse_lookup_starts_from_latest_completed_session(self):
        search_date = latest_completed_nse_session()
        self.fetcher._save_to_db(make_oi_records(search_date))
        session = Mock()
        session.get.return_value = Mock(status_code=404, content=b"")
        self.fetcher.http_session = session

        with patch.object(fetcher_module, "latest_completed_nse_session", return_value=search_date):
            result = self.fetcher.fetch_latest_participant_oi(max_business_days=1)

        requested_token = session.get.call_args.args[0].rsplit("_", 1)[-1].removesuffix(".csv")
        self.assertEqual(requested_token, search_date.strftime("%d%m%Y"))
        self.assertEqual(result["date"], search_date.isoformat())
        self.assertEqual(result["age_days"], (self.today - search_date).days)

    def test_default_nse_lookup_targets_october_fifth_after_close(self):
        session_date = dt.date(2026, 10, 5)
        columns = [
            "Client Type", "Future Index Long", "Future Index Short", "Future Stock Long", "Future Stock Short",
            "Option Index Call Long", "Option Index Put Long", "Option Index Call Short", "Option Index Put Short",
            "Option Stock Call Long", "Option Stock Put Long", "Option Stock Call Short", "Option Stock Put Short",
            "Total Long Contracts", "Total Short Contracts",
        ]
        lines = [",".join(columns)]
        lines.extend(participant + "," + ",".join(["10"] * 14) for participant in PARTICIPANTS)
        session = Mock()
        session.get.return_value = Mock(status_code=200, content=("\n".join(lines)).encode())
        self.fetcher.http_session = session

        with patch.object(fetcher_module, "latest_completed_nse_session", return_value=session_date), \
             patch.object(self.fetcher, "_coerce_date", return_value=session_date):
            result = self.fetcher.fetch_latest_participant_oi(max_business_days=1)

        requested_url = session.get.call_args.args[0]
        self.assertIn("fao_participant_oi_05102026.csv", requested_url)
        self.assertEqual(result["date"], session_date.isoformat())
        self.assertEqual(result["data_status"], "live")


def sqlite_connect(path):
    import sqlite3
    return sqlite3.connect(path)


class CalculatorIntegrityTests(unittest.TestCase):
    def test_october_holiday_gap_preserves_three_session_t2_context(self):
        rows = []
        for session_date, net in (
            (dt.date(2026, 10, 5), 1300),
            (dt.date(2026, 10, 1), 1200),
            (dt.date(2026, 9, 30), 1100),
        ):
            rows.extend(make_oi_records(session_date, net))

        result = InstitutionalCalculator(pd.DataFrame(rows)).calculate_latest_sheet()

        self.assertEqual(result["date"], "2026-10-05")
        self.assertIsNotNone(result["sheet_sections"]["Index Futures"][0]["carried_t2"])
        self.assertIsNone(result["fii_stk_flow_3d"])
        self.assertIsNone(result["fii_stk_flow_5d"])
        self.assertEqual(result["fii_stk_flow_3d_sample_days"], 2)
        self.assertEqual(result["fii_stk_flow_5d_sample_days"], 2)

    def test_flow_windows_are_exact_and_not_extrapolated(self):
        today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        three_dates = []
        for offset, net in enumerate((1000, 1010, 1020)):
            three_dates.extend(make_oi_records(today - dt.timedelta(days=offset), net))
        short_result = InstitutionalCalculator(pd.DataFrame(three_dates)).calculate_latest_sheet()
        self.assertIsNone(short_result["fii_stk_flow_3d"])
        self.assertIsNone(short_result["fii_stk_flow_5d"])
        self.assertFalse(short_result["fii_stk_flow_3d_complete"])
        self.assertFalse(short_result["fii_stk_flow_5d_complete"])
        self.assertEqual(short_result["fii_stk_flow_3d_sample_days"], 2)
        self.assertEqual(short_result["cis_score"], 0.0)

        # Even if extrapolating the two observed changes would cross the +20k
        # threshold, an incomplete 3-day window is unavailable and scores no flow tier.
        two_changes = []
        for offset, net in enumerate((52200, 41200, 30200)):
            two_changes.extend(make_oi_records(today - dt.timedelta(days=offset), net))
        incomplete_result = InstitutionalCalculator(pd.DataFrame(two_changes)).calculate_latest_sheet()
        self.assertIsNone(incomplete_result["fii_stk_flow_3d"])
        self.assertEqual(incomplete_result["cis_score"], 0.0)
        self.assertNotIn("FII 3-Day Stock Accumulation (+)", [name for name, _ in incomplete_result["cis_breakdown"]])

        four_dates = []
        for offset, net in enumerate((40000, 30000, 20000, 10000)):
            four_dates.extend(make_oi_records(today - dt.timedelta(days=offset), net))
        three_day_result = InstitutionalCalculator(pd.DataFrame(four_dates)).calculate_latest_sheet()
        self.assertEqual(three_day_result["fii_stk_flow_3d"], 30000)
        self.assertIsNone(three_day_result["fii_stk_flow_5d"])
        self.assertEqual(three_day_result["cis_score"], 2.0)
        self.assertIn("FII 3-Day Stock Accumulation (+)", [name for name, _ in three_day_result["cis_breakdown"]])

        six_dates = []
        for offset, net in enumerate((1050, 1040, 1030, 1020, 1010, 1000)):
            six_dates.extend(make_oi_records(today - dt.timedelta(days=offset), net))
        full_result = InstitutionalCalculator(pd.DataFrame(six_dates)).calculate_latest_sheet()
        self.assertEqual(full_result["fii_stk_flow_3d"], 30)
        self.assertEqual(full_result["fii_stk_flow_5d"], 50)
        self.assertTrue(full_result["fii_stk_flow_3d_complete"])
        self.assertTrue(full_result["fii_stk_flow_5d_complete"])

    def test_calculator_rejects_large_gap_in_recent_flow_window(self):
        today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        rows = []
        for offset in range(5):
            rows.extend(make_oi_records(today - dt.timedelta(days=offset), 1000 + offset))
        rows.extend(make_oi_records(today - dt.timedelta(days=800), 900))
        with self.assertRaisesRegex(ValueError, "gap"):
            InstitutionalCalculator(pd.DataFrame(rows))


class MacroFetchTests(unittest.TestCase):
    def test_macro_feeds_use_actual_symbols_and_convert_tnx_units(self):
        today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        idx = pd.DatetimeIndex([today - dt.timedelta(days=1), today])
        seen = []

        def downloader(symbol, **kwargs):
            seen.append((symbol, kwargs))
            values = [43.5, 44.0] if symbol == "^TNX" else [100.0, 101.0]
            return yahoo_multiindex(symbol, values, index=idx)

        fetcher = FreeDataFetcher(yahoo_downloader=downloader)
        macro = fetcher.fetch_global_macro()
        self.assertEqual(len(seen), 7)
        self.assertEqual(macro["us_10y_yield"]["current"], 4.4)
        self.assertAlmostEqual(macro["us_10y_yield"]["previous"], 4.35)
        self.assertEqual(macro["nifty_50"]["symbol"], "^NSEI")
        self.assertEqual(macro["nifty_50"]["current"], 101.0)
        self.assertEqual(macro["nifty_50"]["status"], "ok")
        self.assertNotIn("NIFTYBEES.NS", [symbol for symbol, _ in seen])
        self.assertTrue(all(kwargs["timeout"] == 8 for _, kwargs in seen))

    def test_missing_macro_is_none_not_zero_or_neutral(self):
        fetcher = FreeDataFetcher(yahoo_downloader=lambda *_a, **_k: pd.DataFrame())
        macro = fetcher.fetch_global_macro()
        self.assertEqual(len(macro), 7)
        self.assertTrue(all(entry["status"] == "unavailable" for entry in macro.values()))
        self.assertTrue(all(entry["current"] is None for entry in macro.values()))

    def test_sector_strength_uses_documented_relative_blend_and_fresh_index_feeds(self):
        today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        dates = pd.bdate_range(end=today, periods=25)
        bench_close = np.linspace(100, 124, 25)
        sector_close = np.linspace(100, 140, 25)
        histories = {
            "^NSEI": pd.DataFrame({"Open": bench_close, "High": bench_close + 1, "Low": bench_close - 1,
                                    "Close": bench_close, "Volume": 1000}, index=dates),
            "^CNXIT": pd.DataFrame({"Open": sector_close, "High": sector_close + 1, "Low": sector_close - 1,
                                    "Close": sector_close, "Volume": 1000}, index=dates),
        }
        items = [
            {"name": "Nifty 50", "index_symbol": "^NSEI", "history_proxy": None, "category": "Broad Market", "description": "test"},
            {"name": "Nifty IT", "index_symbol": "^CNXIT", "history_proxy": None, "category": "Sectoral", "description": "test"},
        ]
        with patch.object(fetcher_module, "INDEX_UNIVERSE", items), patch.object(
            fetcher_module, "symbols_for_history", side_effect=lambda item: [item["index_symbol"]] if item.get("index_symbol") else []
        ), patch.object(fetcher_module, "download_yahoo", side_effect=lambda symbol, **_kw: histories[symbol].copy()):
            fetcher = FreeDataFetcher()
            result = fetcher.fetch_sector_strength()
        self.assertEqual(len(result), 1)
        self.assertEqual(fetcher.last_sector_diagnostics["status"], "ok")
        self.assertEqual(fetcher.last_sector_diagnostics["scanned_indices"], 1)
        row = result[0]
        bench_1w = (bench_close[-1] / bench_close[-5] - 1) * 100
        bench_1m = (bench_close[-1] / bench_close[-22] - 1) * 100
        sector_1w = (sector_close[-1] / sector_close[-5] - 1) * 100
        sector_1m = (sector_close[-1] / sector_close[-22] - 1) * 100
        expected = round(0.6 * (sector_1w - bench_1w) + 0.4 * (sector_1m - bench_1m), 2)
        self.assertEqual(row["rs_score"], expected)
        self.assertEqual(row["ticker"], "^CNXIT")


if __name__ == "__main__":
    unittest.main()
