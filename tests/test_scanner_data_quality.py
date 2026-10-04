import datetime as dt
import os
import sys
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import index_sweep_engine as daily_module
import mtf_index_sweep_engine as mtf_module
import weekly_index_sweep_engine as weekly_module
from index_sweep_engine import IndexSweepEngine
from market_data import MarketDataError
from mtf_index_sweep_engine import MTFIndexSweepEngine
from weekly_index_sweep_engine import WeeklyIndexSweepEngine


def daily_bars(count=320, flat=False):
    today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
    index = pd.bdate_range(end=today, periods=count)
    close = np.full(count, 100.0) if flat else np.linspace(90, 120, count)
    return pd.DataFrame(
        {"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": np.full(count, 1000)},
        index=index,
    )


def test_index(name="Nifty Test"):
    return {"name": name, "index_symbol": "^TEST", "history_proxy": None, "category": "Broad Market", "description": "test index"}


class ScannerCoverageTests(unittest.TestCase):
    def test_daily_scan_reports_coverage_and_keeps_legacy_list_api(self):
        data = daily_bars(count=100)
        with patch.object(daily_module, "INDEX_UNIVERSE", [test_index()]), patch.object(
            daily_module, "download_yahoo", return_value=data
        ):
            result = IndexSweepEngine().scan_all_indices_detailed(lookback_days=60)
            legacy = IndexSweepEngine().scan_all_indices(lookback_days=60)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scanned_indices"], 1)
        self.assertEqual(result["failed_indices"], [])
        self.assertEqual(legacy, result["setups"])

    def test_daily_feed_failure_is_not_misreported_as_no_signal(self):
        with patch.object(daily_module, "INDEX_UNIVERSE", [test_index()]), patch.object(
            daily_module, "download_yahoo", side_effect=MarketDataError("offline")
        ):
            result = IndexSweepEngine().scan_all_indices_detailed()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["scanned_indices"], 0)
        self.assertEqual(result["failed_indices"], ["Nifty Test"])
        self.assertIn("offline", result["errors"][0]["reason"])

    def test_weekly_scan_uses_recent_bars_and_records_unavailable_coverage(self):
        data = daily_bars(count=320)
        with patch.object(weekly_module, "INDEX_UNIVERSE", [test_index()]), patch.object(
            weekly_module, "download_yahoo", return_value=data
        ):
            result = WeeklyIndexSweepEngine().scan_weekly_indices()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scanned_indices"], 1)

        with patch.object(weekly_module, "INDEX_UNIVERSE", [test_index()]), patch.object(
            weekly_module, "download_yahoo", side_effect=MarketDataError("offline")
        ):
            failed = WeeklyIndexSweepEngine().scan_weekly_indices()
        self.assertEqual(failed["status"], "unavailable")
        self.assertEqual(failed["failed_indices"], ["Nifty Test"])
        self.assertIn("offline", failed["failure_reasons"][0]["reason"])

    def test_mtf_scan_records_daily_feed_failure_with_index_name(self):
        with patch.object(mtf_module, "INDEX_UNIVERSE", [test_index()]), patch.object(
            mtf_module, "download_yahoo", side_effect=MarketDataError("offline")
        ):
            result = MTFIndexSweepEngine().scan_all_indices()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["scanned_indices"], 0)
        self.assertEqual(result["failed_indices"], ["Nifty Test"])
        self.assertEqual(result["errors"][0]["name"], "Nifty Test")
        self.assertEqual(result["errors"][0]["timeframe"], "1d")

    def test_mtf_can_complete_daily_scan_without_an_intraday_request_if_no_trap(self):
        data = daily_bars(count=100, flat=True)
        with patch.object(mtf_module, "INDEX_UNIVERSE", [test_index()]), patch.object(
            mtf_module, "download_yahoo", return_value=data
        ) as download:
            result = MTFIndexSweepEngine().scan_all_indices()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scanned_indices"], 1)
        self.assertEqual(result["setups"], [])
        download.assert_called_once()

    def test_mtf_intraday_feed_failure_marks_scan_partial(self):
        data = daily_bars(count=100)
        ref = mtf_module._ref_date()
        current_week = pd.DataFrame(
            {"Open": [101.0], "High": [102.0], "Low": [99.0], "Close": [101.0], "Volume": [1000]},
            index=pd.DatetimeIndex([pd.Timestamp(ref)]),
        )
        with patch.object(mtf_module, "INDEX_UNIVERSE", [test_index()]), patch.object(
            mtf_module, "download_yahoo", side_effect=[data, MarketDataError("intraday offline")]
        ), patch.object(mtf_module, "_weekly_levels", return_value=(110.0, 100.0)), patch.object(
            mtf_module, "_current_week", return_value=current_week
        ):
            result = MTFIndexSweepEngine().scan_all_indices()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["scanned_indices"], 1)
        self.assertEqual(result["setups"][0]["status"], "PENDING_15M_DATA")
        self.assertEqual(result["errors"][0]["timeframe"], "15m")
        self.assertIn("intraday offline", result["errors"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
