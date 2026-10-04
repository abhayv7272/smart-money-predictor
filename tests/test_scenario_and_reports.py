import datetime as dt
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from main import _price_for_completed_session
from nifty_scenario_engine import NiftyScenarioEngine
from report_generator import ReportGenerator
from weekly_index_sweep_engine import WeeklyIndexSweepEngine


class NiftyScenarioEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = NiftyScenarioEngine()

    def test_imported_model_reproduces_archive_snapshot_probabilities(self):
        # Regression check against the supplied archive's 2026-10-01 live input snapshot.
        # This is only a test fixture; production runs never use it as current data.
        inputs = {
            "nifty": 22422.0,
            "india_vix": 14.46,
            "india_vix_pct": 72.5,
            "us_vix": 16.34,
            "us_vix_pct": 33.5,
            "rsi14": 22.6,
            "dist200": -7.18,
            "dd252": -14.84,
            "dist6mlow": 0.0,
            "bull_count": 0,
            "atoms": {},
            "as_of": "2026-10-01",
        }
        result = self.engine.predict_from_inputs(inputs)
        self.assertTrue(result["available"])
        self.assertAlmostEqual(result["probabilities"]["y_up_1M"]["calibrated"], 0.6583, places=3)
        self.assertAlmostEqual(result["probabilities"]["y_up_3M"]["calibrated"], 0.8379, places=3)
        self.assertAlmostEqual(result["probabilities"]["y_dip5_3M"]["calibrated"], 0.3533, places=3)
        self.assertEqual(result["confidence_bucket"]["bucket"], 5)
        self.assertEqual(result["accuracy"]["nifty_dir_1M"], 62.8)
        self.assertEqual(result["accuracy"]["nifty_base_1M"], 64.1)
        self.assertEqual(result["accuracy"]["nifty_dir_3M"], 62.8)
        self.assertEqual(result["accuracy"]["nifty_base_3M"], 66.7)
        self.assertEqual(result["probabilities"]["y_up_1M"]["oos_hit_pct"], 62.8)
        self.assertEqual(result["probabilities"]["y_up_1M"]["base_rate_pct"], 64.1)
        self.assertEqual(result["probabilities"]["y_up_3M"]["oos_hit_pct"], 62.8)
        self.assertEqual(result["probabilities"]["y_up_3M"]["base_rate_pct"], 66.7)
        self.assertEqual(
            [row["key"] for row in result["matched_scenarios"]],
            ["slow_bleed", "deep_oversold_fear", "retest", "local_fear"],
        )

        changed_inputs = dict(inputs, us_vix_pct=90.0, india_vix_pct=10.0)
        fresh_result = self.engine.predict_from_inputs(changed_inputs)
        self.assertNotEqual(
            fresh_result["probabilities"]["y_up_1M"]["calibrated"],
            result["probabilities"]["y_up_1M"]["calibrated"],
        )
        self.assertEqual(fresh_result["accuracy"], result["accuracy"])

    def test_live_spot_is_rejected_unless_it_matches_latest_completed_nse_session(self):
        expected = dt.date(2026, 10, 5)
        self.assertEqual(
            _price_for_completed_session(22422.0, "2026-10-05", expected),
            22422.0,
        )
        self.assertIsNone(_price_for_completed_session(22422.0, "2026-10-01", expected))
        self.assertIsNone(_price_for_completed_session(0, "2026-10-05", expected))

    def test_live_feature_builder_lags_us_vix_one_indian_session(self):
        idx = pd.bdate_range("2024-01-01", periods=320)
        n = np.arange(len(idx), dtype=float)
        history = pd.DataFrame(
            {
                "nifty": 19000 + n * 4 + np.sin(n / 7) * 45,
                "india_vix": 15 + np.sin(n / 11) * 3 + n * 0.005,
                "us_vix": 14 + n * 0.02 + np.cos(n / 9),
            },
            index=idx,
        )
        result = self.engine.build_inputs(history)
        self.assertEqual(result["us_vix"], round(float(history["us_vix"].iloc[-2]), 2))
        lagged = history["us_vix"].shift(1)
        expected_percentile = round(float((lagged.iloc[-1] > lagged.iloc[-253:-1]).mean() * 100), 1)
        self.assertEqual(result["us_vix_pct"], expected_percentile)
        self.assertEqual(result["as_of"], idx[-1].date().isoformat())
        self.assertIn("bull_count", result)
        self.assertLessEqual(result["bull_count"], 7)

    def test_missing_live_history_never_falls_back_to_embedded_forecast(self):
        result = self.engine.run(history=pd.DataFrame())
        self.assertFalse(result["available"])
        self.assertIn("No aligned market history", result["error"])

    def test_missing_latest_india_vix_is_not_hidden_by_forward_fill(self):
        idx = pd.bdate_range("2024-01-01", periods=320)
        n = np.arange(len(idx), dtype=float)
        history = pd.DataFrame(
            {
                "nifty": 19000 + n * 4,
                "india_vix": 15 + np.sin(n / 11),
                "us_vix": 14 + np.cos(n / 9),
            },
            index=idx,
        )
        history.loc[idx[-1], "india_vix"] = np.nan
        with self.assertRaisesRegex(ValueError, "missing on the latest NIFTY session"):
            self.engine.build_inputs(history)


class ReportIntegrationTests(unittest.TestCase):
    def test_scenario_and_weekly_diagnostics_appear_in_both_report_formats(self):
        scenario = NiftyScenarioEngine().predict_from_inputs(
            {
                "nifty": 22422.0,
                "india_vix": 14.46,
                "india_vix_pct": 72.5,
                "us_vix": 16.34,
                "us_vix_pct": 33.5,
                "rsi14": 22.6,
                "dist200": -7.18,
                "dd252": -14.84,
                "dist6mlow": 0.0,
                "bull_count": 0,
                "atoms": {},
                "as_of": "2026-10-01",
            }
        )
        calc = {
            "date": "2026-10-02",
            "display_date": "02 October 2026",
            "cis_score": 1.5,
            "fii_long_ratio": 44.0,
            "fii_stk_flow_3d": 12000,
            "sheet_sections": {},
            "traps": [],
        }
        regime = {
            "regime_id": 3,
            "regime_name": "Regime 3: Full Momentum Markup",
            "regime_desc": "Institutional flow is balanced.",
            "regime_color": "#059669",
            "primary_signal": "HOLD & TRAIL SL",
            "signal_color": "#F59E0B",
            "capital_allocation_pct": 70,
            "cash_reserve_pct": 30,
            "action_instructions": "Hold core swing positions with risk controls.",
            "trajectory": "Range-bound around support and resistance.",
            "resistance_2": 22800,
            "resistance_1": 22600,
            "support_1": 22200,
            "support_2": 22000,
            "sweep_zone": 22150,
        }
        sectors = {
            "rotation_summary": "No sector data in this test.",
            "all_sectors": [],
            "feed_coverage": {
                "total_indices": 16,
                "scanned_indices": 14,
                "failed_indices": ["Nifty IT", "Nifty Auto"],
                "errors": [{"name": "Nifty IT", "reason": "Yahoo timeout"}],
                "status": "partial",
            },
        }
        macro = {
            key: {"current": value, "change_pct": 0.25}
            for key, value in {
                "brent_crude": 80,
                "us_10y_yield": 4,
                "us_dollar_index": 101,
                "dow_jones": 42000,
                "nifty_50": 22422,
            }.items()
        }
        weekly_scan = {
            "total_scanned": 19,
            "scanned_indices": 17,
            "weekly_hits": [],
            "near_misses": [
                {
                    "name": "Nifty Bank",
                    "score": 48,
                    "wick_pct": 35.5,
                    "close_in_range_pct": 65.0,
                    "confluences": ["26-Week Low Swept & Reclaimed"],
                }
            ],
            "failed_indices": ["Nifty CPSE", "Nifty Smallcap 250"],
            "scan_date": "2026-10-02",
            "is_friday": True,
            "status": "partial",
        }

        with tempfile.TemporaryDirectory() as tempdir:
            report = ReportGenerator(output_dir=tempdir).generate_html_report(
                calc,
                regime,
                sectors,
                macro,
                daily_sweep_res={
                    "total_indices": 19,
                    "scanned_indices": 17,
                    "setups": [],
                    "failed_indices": ["Nifty CPSE", "Nifty Smallcap 250"],
                    "scan_date": "2026-10-02",
                    "status": "partial",
                },
                weekly_sweep_res=weekly_scan,
                mtf_res={
                    "has_signals": False,
                    "actionable": [],
                    "triggered": [],
                    "status": "unavailable",
                    "total_indices": 19,
                    "scanned_indices": 0,
                    "errors": [{"name": "Nifty 50", "timeframe": "1d", "reason": "test failure"}],
                },
                scenario_res=scenario,
            )
            with open(report["html_path"], encoding="utf-8") as handle:
                html = handle.read()
            with open(report["md_path"], encoding="utf-8") as handle:
                markdown = handle.read()

        for document in (html, markdown):
            lowered = document.lower()
            self.assertIn("nifty scenario lab", lowered)
            self.assertIn("nse index weekly liquidity sweep radar", lowered)
            self.assertIn("partial", lowered)
            self.assertIn("nifty cpse", lowered)
            self.assertIn("near-miss", lowered)
        self.assertIn("65.8%", html)
        self.assertIn("83.8%", markdown)
        for document in (html, markdown):
            lowered = document.lower()
            self.assertIn("not recalculated or retrained each run", lowered)
            self.assertIn("62.8%", document)
            self.assertIn("64.1%", document)
            self.assertIn("66.7%", document)
        self.assertIn("Live probabilities", markdown)
        self.assertIn("fresh market inputs", html)
        self.assertIn("No qualifying setup in the feeds that were available", html)
        self.assertIn("Partial daily scan", html)
        self.assertIn("MTF scan status: unavailable; daily index history coverage 0/19", html)
        self.assertIn("MTF scan status", markdown)
        self.assertIn("PARTIAL — 14/16 sector histories usable", html)
        self.assertIn("Yahoo timeout", markdown)
        self.assertIn("not a no-signal conclusion", markdown)

    def test_partial_flow_disclosure_preserves_complete_three_day_tier(self):
        summary = ReportGenerator._fii_flow_summary(
            {
                "fii_stk_flow_3d": 30000,
                "fii_stk_flow_5d": None,
                "fii_stk_flow_3d_complete": True,
                "fii_stk_flow_5d_complete": False,
                "fii_stk_flow_3d_sample_days": 3,
                "fii_stk_flow_5d_sample_days": 4,
            }
        )
        self.assertEqual(summary["flow_3d_display"], "+30,000 contracts")
        self.assertEqual(summary["flow_5d_display"], "N/A (only 4/5 daily changes)")
        self.assertIn("3-day tier remains eligible for CIS", summary["cis_note"])
        self.assertIn("5-day tier is omitted", summary["cis_note"])
        self.assertIn("not extrapolated", summary["cis_note"])

    def test_unavailable_spot_and_macro_feeds_render_as_unavailable_not_zero(self):
        from regime_engine import RegimeEngine

        calc = {
            "date": "2026-10-02",
            "display_date": "02 October 2026",
            "cis_score": 0.0,
            "fii_long_ratio": 50.0,
            "fii_stk_flow_3d": None,
            "fii_stk_flow_5d": None,
            "fii_stk_flow_3d_complete": False,
            "fii_stk_flow_5d_complete": False,
            "fii_stk_flow_3d_sample_days": 2,
            "fii_stk_flow_5d_sample_days": 2,
            "sheet_sections": {
                "Index Futures": [
                    {
                        "participant": "FII",
                        "long_action": "Added Longs: +0",
                        "short_action": "Added Shorts: +0",
                        "net_action": "Bought Net: +0",
                        "sentiment": "NEUTRAL",
                        "carried_sentiment": "NEUTRAL",
                        "carried_t0": 20,
                        "carried_t1": 20,
                        "carried_t2": 20,
                    }
                ]
            },
            "traps": [],
        }
        macro = {
            key: {"symbol": symbol, "current": None, "previous": None, "change_pct": None,
                  "status": "unavailable", "error": "no feed"}
            for key, symbol in {
                "brent_crude": "BZ=F", "us_10y_yield": "^TNX", "us_dollar_index": "DX-Y.NYB",
                "dow_jones": "^DJI", "sp500": "^GSPC", "nifty_50": "^NSEI", "bank_nifty": "^NSEBANK",
            }.items()
        }
        regime = RegimeEngine().evaluate_regime_and_action(calc, macro, nifty_current_price=None)
        self.assertEqual(regime["primary_signal"], "NO TRADE — FRESH NIFTY DATA UNAVAILABLE")
        self.assertEqual(regime["capital_allocation_pct"], 0)
        self.assertEqual(regime["cash_reserve_pct"], 100)
        self.assertEqual(regime["trajectory_type"], "DATA_UNAVAILABLE")
        with tempfile.TemporaryDirectory() as tempdir:
            report = ReportGenerator(output_dir=tempdir).generate_html_report(
                calc, regime, {"all_sectors": [], "rotation_summary": "Sector data unavailable."}, macro,
                daily_sweep_res={"total_indices": 19, "scanned_indices": 0, "failed_indices": ["Nifty 50"],
                                 "setups": [], "scan_date": "2026-10-02", "status": "unavailable"},
                weekly_sweep_res=None,
                mtf_res={"has_signals": False, "status": "unavailable", "total_indices": 19,
                         "scanned_indices": 0, "errors": []},
                scenario_res={"available": False, "error": "offline"},
            )
            with open(report["html_path"], encoding="utf-8") as handle:
                html = handle.read()
            with open(report["md_path"], encoding="utf-8") as handle:
                markdown = handle.read()
        self.assertIn("NO TRADE — FRESH NIFTY DATA UNAVAILABLE", html)
        self.assertIn("NO TRADE — FRESH NIFTY DATA UNAVAILABLE", markdown)
        self.assertTrue(all(line == line.rstrip() for line in html.splitlines()))
        self.assertIn("Unavailable", html)
        self.assertIn("Insufficient history (2/3 daily changes)", html)
        self.assertIn("Insufficient history (2/5 daily changes)", html)
        self.assertIn("N/A (only 2/3 daily changes)", html)
        self.assertIn("N/A (only 2/5 daily changes)", markdown)
        for document in (html, markdown):
            self.assertIn("Missing changes are not extrapolated", document)
            self.assertIn("omitted from CIS", document)
            self.assertIn("can differ from earlier runs", document)
        self.assertIn("2 Sessions Ago", html)
        self.assertIn(">20</td>", html)
        self.assertIn("Unavailable", html)
        self.assertIn("Unavailable", markdown)
        self.assertNotIn("23,900", html)

    def test_weekly_scan_can_generate_a_real_qualifying_index_setup(self):
        engine = WeeklyIndexSweepEngine()
        idx = pd.date_range("2025-01-03", periods=60, freq="W-FRI")
        weekly = pd.DataFrame(
            {
                "Open": [104.0] * 59 + [104.0],
                "High": [108.0] * 59 + [106.0],
                "Low": [100.0] * 59 + [95.0],
                "Close": [105.0] * 59 + [105.0],
                "Volume": [1000] * 60,
            },
            index=idx,
        )
        item = {
            "name": "Nifty 50",
            "index_symbol": "^NSEI",
            "category": "Broad Market",
            "description": "Test index",
        }
        hit = engine._evaluate(weekly, item, "^NSEI")
        self.assertIsNotNone(hit)
        self.assertTrue(hit["has_setup"])
        self.assertEqual(hit["data_source"], "actual_index")
        self.assertEqual(hit["pool_type"], "26-Week Low")


if __name__ == "__main__":
    unittest.main()
