import os
import sys
import json
import datetime
from zoneinfo import ZoneInfo
from fetcher import FreeDataFetcher
from calculator import InstitutionalCalculator
from regime_engine import RegimeEngine
from sector_rotation import SectorRotationAnalyzer
from index_sweep_engine import IndexSweepEngine
from weekly_index_sweep_engine import WeeklyIndexSweepEngine
from mtf_index_sweep_engine import MTFIndexSweepEngine
from report_generator import ReportGenerator
from email_sender import EmailSender

def run_daily_prediction(force_weekly=False):
    # Determine Friday explicitly in India timezone, independent of the GitHub runner timezone.
    india_now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    is_friday = (india_now.weekday() == 4) or force_weekly or ("--weekly" in sys.argv)
    
    print("="*80)
    edition_title = "🏛️  SMART MONEY INSTITUTIONAL PREDICTION ENGINE (PRO EDITION)"
    if is_friday:
        edition_title += " [🗓️ FRIDAY WEEKLY CONFLUENCE SPECIAL]"
    print(edition_title)
    print("="*80)
    
    # 1. Fetch Latest Data
    print("\n[1/6] Fetching Official 100% Free Data...")
    fetcher = FreeDataFetcher()
    latest_oi = fetcher.fetch_latest_participant_oi()
    print(f"      • Latest Participant OI Date: {latest_oi['display_date']} ({latest_oi['status']})")
    
    macro_data = fetcher.fetch_global_macro()
    nifty_px = macro_data.get("nifty_50", {}).get("current", 24200.0)
    print(f"      • Nifty Current Spot: {nifty_px:,.2f} | Brent Crude: ${macro_data.get('brent_crude', {}).get('current', 0)}/bbl")
    
    raw_sectors = fetcher.fetch_sector_strength()
    print(f"      • Sector Rotation Data: Fetched {len(raw_sectors)} key sectors.")
    
    # 2. Multi-day History & Calculation
    print("\n[2/6] Calculating Amit Dhamija Multi-Day Sheets & Institutional Flow...")
    hist_df = fetcher.fetch_recent_history(days_count=10)
    calculator = InstitutionalCalculator(hist_df)
    calc_res = calculator.calculate_latest_sheet()
    
    cis = calc_res["cis_score"]
    fii_ratio = calc_res["fii_long_ratio"]
    fii_stk_3d = calc_res["fii_stk_flow_3d"]
    print(f"      • FII Long Ratio: {fii_ratio}% | FII 3-Day Stock Flow: {fii_stk_3d:+,} contracts")
    print(f"      • Composite Institutional Score (CIS): {cis:+.1f} / 10")
    
    # 3. Regime & Action Assignment
    print("\n[3/6] Assigning Market Regime & Capital Allocation...")
    regime_engine = RegimeEngine()
    regime_res = regime_engine.evaluate_regime_and_action(calc_res, macro_data, nifty_px)
    
    print(f"      • Market Regime: {regime_res['regime_name']}")
    print(f"      • Primary Signal: {regime_res['primary_signal']}")
    print(f"      • Capital Exposure: {regime_res['capital_allocation_pct']}% Stocks | {regime_res['cash_reserve_pct']}% Cash")
    
    # 4. Sector Rotation Analysis
    print("\n[4/6] Analyzing Institutional Sector Leadership...")
    sector_analyzer = SectorRotationAnalyzer()
    sector_res = sector_analyzer.analyze_sectors(raw_sectors)
    top_leaders = [s["name"] for s in sector_res.get("top_leaders", [])]
    print(f"      • Top Outperforming Sectors: {', '.join(top_leaders) if top_leaders else 'Broad-based'}")
    
    # 5. Daily Index Liquidity Sweep & Reversal Confluence Engine (Runs EVERY DAY)
    print("\n[5/6] Scanning ALL NSE Indices for Daily Liquidity Sweeps...")
    sweep_engine = IndexSweepEngine()
    daily_sweep_res = sweep_engine.scan_all_indices()
    high_grade_sweeps = [s for s in daily_sweep_res if s.get("score", 0) >= 50]
    print(f"      • Active Daily Sweep Setups Found: {len(daily_sweep_res)} indices ({len(high_grade_sweeps)} Grade A+/B High Conviction)")
    
    # 6. Weekly Index Liquidity Sweep Radar (Runs WEEKLY ON FRIDAY ONLY)
    weekly_sweep_res = None
    if is_friday:
        print("\n[FRIDAY SPECIAL] Scanning ALL NSE Indices for Weekly Liquidity Sweeps (Weekly-Sweep Engine)...")
        weekly_engine = WeeklyIndexSweepEngine()
        weekly_scan = weekly_engine.scan_weekly_indices()
        weekly_sweep_res = weekly_scan.get("weekly_hits", [])
        print(f"      • Weekly Sweep Hits Found: {len(weekly_sweep_res)} indices across Broad, Sectoral & Thematic categories.")
    else:
        print("\n[NOTE] Weekly Index Sweep Radar is scheduled for Friday market close (Runs 1x per week).")
    
    # MTF Index Radar: calculate every weekday, but show prominently only when an index signal exists.
    print("\n[MTF] Scanning NSE indices: Previous-Week PWL → Daily Trap → causal 15-min MSS...")
    mtf_res = MTFIndexSweepEngine().scan_all_indices()
    print(f"      • MTF index setups: {len(mtf_res['setups'])} | Active triggers: {len(mtf_res['triggered'])}")

    # 7. Generate Visual Reports & Send Email
    print("\n[6/6] Generating Ultra-Stunning HTML Dashboard & Dispatching...")
    report_gen = ReportGenerator()
    rep_res = report_gen.generate_html_report(calc_res, regime_res, sector_res, macro_data, daily_sweep_res, weekly_sweep_res, mtf_res)
    print(f"      • HTML Dashboard saved to: {rep_res['html_path']}")
    print(f"      • Latest Dashboard saved to: {rep_res['latest_html_path']}")
    print(f"      • Markdown Report saved to: {rep_res['md_path']}")
    
    # Send Email
    email_sender = EmailSender(recipient_email=fetcher.config.get("recipient_email", "abhayv7272@gmail.com"))
    subject_suffix = " | 🗓️ Friday Weekly Edition" if is_friday else ""
    subject = f"🏛️ Smart Money Prediction ({calc_res['display_date']}): {regime_res['primary_signal']} | CIS {cis:+.1f} | Regime {regime_res['regime_id']}{subject_suffix}"
    email_sender.send_report(subject, rep_res["html_content"])
    
    print("\n" + "="*80)
    print("✅ PREDICTION COMPLETED SUCCESSFULLY!")
    print(f"   Signal        : {regime_res['primary_signal']}")
    print(f"   Allocation    : {regime_res['capital_allocation_pct']}% Stocks / {regime_res['cash_reserve_pct']}% Cash")
    print(f"   Daily Sweeps  : {len(daily_sweep_res)} Setups Active")
    if is_friday:
        print(f"   Weekly Sweeps : {len(weekly_sweep_res) if weekly_sweep_res else 0} Multi-Week Structural Sweeps (Friday Radar Active)")
    print(f"   Target Swings : 10 to 40 Days Holding in Leading Stage-2 Sectors")
    print("="*80 + "\n")
    
    return rep_res

if __name__ == "__main__":
    # Ensure current directory is in path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    force_weekly = "--weekly" in sys.argv
    run_daily_prediction(force_weekly=force_weekly)
