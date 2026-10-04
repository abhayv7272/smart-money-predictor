import os
import sys
import datetime
from html import escape
from zoneinfo import ZoneInfo

from fetcher import FreeDataFetcher
from calculator import InstitutionalCalculator
from regime_engine import RegimeEngine
from sector_rotation import SectorRotationAnalyzer
from index_sweep_engine import IndexSweepEngine
from weekly_index_sweep_engine import WeeklyIndexSweepEngine
from mtf_index_sweep_engine import MTFIndexSweepEngine
from nifty_scenario_engine import NiftyScenarioEngine
from report_generator import ReportGenerator
from email_sender import EmailSender
from nse_calendar import latest_completed_nse_session


def _valid_positive_number(value):
    try:
        number = float(value)
        return number if number > 0 and number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _price_for_completed_session(value, as_of, expected_session):
    """Accept an NSE index price only when it is dated to the last completed session."""
    expected_date = expected_session.isoformat() if hasattr(expected_session, "isoformat") else str(expected_session)
    if str(as_of) != expected_date:
        return None
    return _valid_positive_number(value)


def run_daily_prediction(force_weekly=False):
    # Determine Friday explicitly in India timezone, independent of the GitHub runner timezone.
    india_now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    is_friday = india_now.weekday() == 4
    include_weekly = is_friday or force_weekly

    print("=" * 80)
    edition_title = "🏛️  SMART MONEY INSTITUTIONAL PREDICTION ENGINE (PRO EDITION)"
    if is_friday:
        edition_title += " [🗓️ FRIDAY WEEKLY CONFLUENCE SPECIAL]"
    elif force_weekly:
        edition_title += " [🗓️ MANUAL WEEKLY SCAN]"
    print(edition_title)
    print("=" * 80)

    # Fetch and validate the critical official OI input first. A broken/old OI history
    # must stop signal generation rather than be converted into a current report.
    print("\n[1/7] Fetching official NSE participant OI and validating recent history...")
    fetcher = FreeDataFetcher()
    try:
        latest_oi = fetcher.fetch_latest_participant_oi()
        print(
            f"      • Latest Participant OI: {latest_oi['display_date']} "
            f"({latest_oi.get('data_status', latest_oi['status'])}, source={latest_oi.get('source')}, "
            f"age={latest_oi.get('age_days', 'unknown')} day(s))"
        )
        hist_df = fetcher.fetch_recent_history(days_count=10)
        calculator = InstitutionalCalculator(hist_df)
        calc_res = calculator.calculate_latest_sheet()
        calc_res["oi_source"] = latest_oi.get("source")
        calc_res["oi_data_status"] = latest_oi.get("data_status", latest_oi.get("status"))
        calc_res["oi_age_days"] = latest_oi.get("age_days")
    except Exception as exc:
        # Do not emit a stale/invalid signal report. If mail is configured, deliver an
        # explicit blocked-run notice so a data-integrity failure is not a silent miss.
        reason = f"{type(exc).__name__}: {exc}"
        failure_html = (
            "<html><body style='font-family:Arial;background:#0b1120;color:#e2e8f0;padding:24px'>"
            "<h2 style='color:#f59e0b'>Smart Money report blocked: participant OI data quality</h2>"
            "<p>No current trading signal was generated because the critical official NSE participant-OI "
            "input was unavailable, stale, incomplete, or discontinuous.</p>"
            f"<pre style='white-space:pre-wrap;color:#cbd5e1'>{escape(reason)}</pre>"
            "<p>Resolve the feed/history issue, then rerun the daily workflow. No stale OI flows were extrapolated.</p>"
            "</body></html>"
        )
        try:
            EmailSender(recipient_email=fetcher.config.get("recipient_email") or "abhayv7272@gmail.com").send_report(
                "Smart Money report blocked by OI data quality", failure_html
            )
        except Exception as mail_exc:
            print(f"[WARN] Could not dispatch critical data-quality notice: {type(mail_exc).__name__}: {mail_exc}")
        raise

    cis = calc_res["cis_score"]
    fii_ratio = calc_res["fii_long_ratio"]
    flow_summary = ReportGenerator._fii_flow_summary(calc_res)
    print(
        f"      • FII Long Ratio: {fii_ratio}% | FII 3-Day Stock Flow: {flow_summary['flow_3d_display']} "
        f"| FII 5-Day Stock Flow: {flow_summary['flow_5d_display']}"
    )
    print(f"      • Composite Institutional Score (CIS): {cis:+.1f} / 10")
    if flow_summary["cis_note"]:
        print(f"      • FII flow/CIS caveat: {flow_summary['cis_note']}")

    # Optional market feeds remain bounded and never produce fabricated neutral values.
    print("\n[2/7] Fetching macro/benchmark feeds and the NIFTY Scenario Lab overlay...")
    macro_data = fetcher.fetch_global_macro()
    try:
        scenario_res = NiftyScenarioEngine().run()
    except Exception as exc:
        scenario_res = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    expected_spot_session = latest_completed_nse_session()
    expected_spot_date = expected_spot_session.isoformat()
    if scenario_res.get("available") and scenario_res.get("as_of") != expected_spot_date:
        scenario_as_of = scenario_res.get("as_of") or "unknown date"
        scenario_res = {
            "available": False,
            "error": (
                f"Scenario inputs are dated {scenario_as_of}; latest completed NSE session is "
                f"{expected_spot_date}. Stale scenario data is not used as current."
            ),
        }

    nifty_entry = macro_data.get("nifty_50", {})
    nifty_px = None
    if nifty_entry.get("status") != "unavailable":
        nifty_px = _price_for_completed_session(
            nifty_entry.get("current"), nifty_entry.get("as_of"), expected_spot_session
        )
        if nifty_px is None:
            actual_as_of = nifty_entry.get("as_of") or "unknown date"
            if actual_as_of != expected_spot_date:
                error = (
                    f"NIFTY close is dated {actual_as_of}; latest completed NSE session is "
                    f"{expected_spot_date}. Stale spot data is not used for the live signal."
                )
            else:
                error = f"NIFTY close for {expected_spot_date} is invalid."
            nifty_entry.update(
                {"current": None, "previous": None, "change_pct": None, "status": "unavailable", "error": error}
            )
            macro_data["nifty_50"] = nifty_entry
            print(f"[WARN] {error}")

    if nifty_px is None and scenario_res.get("available"):
        scenario_inputs = scenario_res.get("inputs", {})
        nifty_px = _price_for_completed_session(
            scenario_inputs.get("nifty"), scenario_res.get("as_of"), expected_spot_session
        )
        if nifty_px is not None:
            # Scenario history is a fresh actual NIFTY index close; preserve that provenance.
            macro_data["nifty_50"] = {
                "symbol": "^NSEI",
                "source": "Yahoo Finance (Scenario Lab history)",
                "current": nifty_px,
                "previous": None,
                "change_pct": None,
                "as_of": scenario_res.get("as_of"),
                "status": "fallback",
                "error": None,
            }
    nifty_text = f"{nifty_px:,.2f}" if nifty_px is not None else "Unavailable"
    brent_px = _valid_positive_number(macro_data.get("brent_crude", {}).get("current"))
    brent_text = f"${brent_px:,.2f}/bbl" if brent_px is not None else "Unavailable"
    print(f"      • Nifty Current Spot: {nifty_text} | Brent Crude: {brent_text}")

    if scenario_res.get("available"):
        scenario_probs = scenario_res["probabilities"]
        print(
            f"      • Scenario P(up 1M/3M): {scenario_probs['y_up_1M']['calibrated']:.1%} / "
            f"{scenario_probs['y_up_3M']['calibrated']:.1%} | "
            f"P(3M >5% dip): {scenario_probs['y_dip5_3M']['calibrated']:.1%} | "
            f"Data as of {scenario_res.get('as_of')}"
        )
    else:
        print(f"      • Scenario overlay unavailable (core report continues): {scenario_res.get('error')}")

    raw_sectors = fetcher.fetch_sector_strength()
    sector_feed_coverage = fetcher.last_sector_diagnostics
    print(
        f"      • Sector Rotation Data: {sector_feed_coverage.get('scanned_indices', len(raw_sectors))}/"
        f"{sector_feed_coverage.get('total_indices', len(raw_sectors))} valid fresh feeds "
        f"({sector_feed_coverage.get('status', 'unknown')})."
    )

    # Regime and NIFTY price levels are calculated only after spot validation.
    print("\n[3/7] Assigning Market Regime & Capital Allocation...")
    regime_engine = RegimeEngine()
    regime_res = regime_engine.evaluate_regime_and_action(calc_res, macro_data, nifty_px)
    print(f"      • Market Regime: {regime_res['regime_name']}")
    print(f"      • Primary Signal: {regime_res['primary_signal']}")
    print(
        f"      • Capital Exposure: {regime_res['capital_allocation_pct']}% Stocks | "
        f"{regime_res['cash_reserve_pct']}% Cash"
    )

    print("\n[4/7] Analyzing institutional sector leadership...")
    sector_res = SectorRotationAnalyzer().analyze_sectors(raw_sectors)
    sector_res["feed_coverage"] = sector_feed_coverage
    top_leaders = [sector["name"] for sector in sector_res.get("top_leaders", [])]
    if top_leaders:
        leader_text = ", ".join(top_leaders)
    elif not raw_sectors:
        leader_text = "Unavailable (no valid sector feeds)"
    else:
        leader_text = "No qualifying leader"
    print(f"      • Top Outperforming Sectors: {leader_text}")

    print("\n[5/7] Scanning NSE indices for daily liquidity sweeps...")
    daily_scan_res = IndexSweepEngine().scan_all_indices_detailed()
    daily_setups = daily_scan_res.get("setups", [])
    high_grade_sweeps = [setup for setup in daily_setups if setup.get("score", 0) >= 50]
    print(
        f"      • Daily setups: {len(daily_setups)} | high grade: {len(high_grade_sweeps)} | "
        f"feed coverage: {daily_scan_res.get('scanned_indices', 0)}/{daily_scan_res.get('total_indices', 0)} "
        f"({daily_scan_res.get('status')})"
    )

    weekly_scan_res = None
    if include_weekly:
        label = "WEEKLY SPECIAL" if is_friday else "MANUAL WEEKLY SCAN"
        print(f"\n[{label}] Scanning NSE indices for completed-week liquidity sweeps...")
        weekly_scan_res = WeeklyIndexSweepEngine().scan_weekly_indices()
        weekly_total = weekly_scan_res.get("total_scanned", 0)
        weekly_scanned = weekly_scan_res.get("scanned_indices", max(weekly_total - len(weekly_scan_res.get("failed_indices", [])), 0))
        print(
            f"      • Weekly scan: {len(weekly_scan_res.get('weekly_hits', []))} setups | "
            f"{len(weekly_scan_res.get('near_misses', []))} near-misses | "
            f"{weekly_scanned}/{weekly_total} feeds available ({weekly_scan_res.get('status')})."
        )
    else:
        print("\n[NOTE] Weekly Index Sweep Radar runs after the completed Friday candle (or with --weekly).")

    print("\n[MTF] Scanning NSE indices: previous-week PWL → daily trap → causal 15-minute MSS...")
    mtf_res = MTFIndexSweepEngine().scan_all_indices()
    print(
        f"      • MTF setups: {len(mtf_res['setups'])} | active triggers: {len(mtf_res['triggered'])} | "
        f"daily feed coverage: {mtf_res.get('scanned_indices', 0)}/{mtf_res.get('total_indices', 0)} "
        f"({mtf_res.get('status')})"
    )

    print("\n[7/7] Generating HTML/Markdown dashboard and dispatching...")
    report_gen = ReportGenerator()
    rep_res = report_gen.generate_html_report(
        calc_res, regime_res, sector_res, macro_data, daily_scan_res,
        weekly_scan_res, mtf_res, scenario_res,
    )
    print(f"      • HTML dashboard saved to: {rep_res['html_path']}")
    print(f"      • Latest dashboard saved to: {rep_res['latest_html_path']}")
    print(f"      • Markdown report saved to: {rep_res['md_path']}")

    email_sender = EmailSender(recipient_email=fetcher.config.get("recipient_email") or "abhayv7272@gmail.com")
    subject_suffix = " | 🗓️ Weekly Sweep Edition" if include_weekly else ""
    subject = (
        f"🏛️ Smart Money Prediction ({calc_res['display_date']}): {regime_res['primary_signal']} | "
        f"CIS {cis:+.1f} | Regime {regime_res['regime_id']}{subject_suffix}"
    )
    email_sent = email_sender.send_report(subject, rep_res["html_content"])

    print("\n" + "=" * 80)
    print("✅ REPORT GENERATION COMPLETED")
    print(f"   Email delivery : {'sent' if email_sent else 'not sent (see delivery log)'}")
    print(f"   Signal        : {regime_res['primary_signal']}")
    print(f"   Allocation    : {regime_res['capital_allocation_pct']}% Stocks / {regime_res['cash_reserve_pct']}% Cash")
    print(
        f"   Daily Sweeps  : {len(daily_setups)} setups "
        f"({daily_scan_res.get('scanned_indices', 0)}/{daily_scan_res.get('total_indices', 0)} feeds)"
    )
    if include_weekly:
        print(
            f"   Weekly Sweeps : {len(weekly_scan_res.get('weekly_hits', []))} qualifying setups "
            f"({len(weekly_scan_res.get('near_misses', []))} near-misses; "
            f"{weekly_scan_res.get('scanned_indices', 0)}/{weekly_scan_res.get('total_scanned', 0)} feeds)"
        )
    print("   Target Swings : 10 to 40 Days Holding in Leading Stage-2 Sectors")
    print("=" * 80 + "\n")
    return rep_res


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    run_daily_prediction(force_weekly="--weekly" in sys.argv)
