import os
import datetime
from signal_chart_renderer import chart_html
from scenario_lab_report import (
    load_scenario_lab_data,
    render_scenario_lab_html,
    render_scenario_lab_markdown,
)

class ReportGenerator:
    def __init__(self, output_dir="reports"):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.output_dir = os.path.join(self.base_dir, output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_html_report(self, calc_res, regime_res, sector_res, macro_res, daily_sweep_res=None, weekly_sweep_res=None, mtf_res=None):
        date_str = calc_res["date"]
        display_date = calc_res["display_date"]
        cis = calc_res["cis_score"]
        fii_ratio = calc_res["fii_long_ratio"]
        fii_stk_3d = calc_res["fii_stk_flow_3d"]
        
        regime_name = regime_res["regime_name"]
        regime_desc = regime_res["regime_desc"]
        signal = regime_res["primary_signal"]
        signal_color = regime_res["signal_color"]
        cap_pct = regime_res["capital_allocation_pct"]
        cash_pct = regime_res["cash_reserve_pct"]
        action_text = regime_res["action_instructions"]
        
        daily_sweep_res = daily_sweep_res or []
        is_friday_report = weekly_sweep_res is not None
        mtf_res = mtf_res or {"has_signals": False, "actionable": [], "triggered": []}
        scenario_lab_data = load_scenario_lab_data(
            os.path.join(self.base_dir, "nifty-scenario-lab-github.zip")
        )
        scenario_lab_html = render_scenario_lab_html(scenario_lab_data, date_str)

        # Signal-only MTF section: suppressed completely when no index trap/MSS exists.
        mtf_section_html = ""
        if mtf_res.get("has_signals"):
            mtf_rows = ""
            mtf_chart_blocks = ""
            for m in mtf_res.get("actionable", []):
                status = m.get("status", "PENDING")
                color = "#10B981" if status == "TRIGGERED_ACTIVE" else "#F59E0B"
                entry = f"{m['entry']:,.2f}" if m.get("entry") is not None else "Waiting"
                sl = f"{m['stoploss']:,.2f}" if m.get("stoploss") is not None else "—"
                t1 = f"{m['target_1']:,.2f}" if m.get("target_1") is not None else "—"
                rr = f"{m['rr_t2']:.2f}R" if m.get("rr_t2") is not None else "—"
                mtf_rows += f'''<tr style="border-bottom:1px solid #1E293B">
                <td style="padding:10px;color:#F8FAFC;font-weight:700">{m['name']}</td>
                <td style="padding:10px;color:{color};font-weight:800">{status.replace('_',' ')}</td>
                <td style="padding:10px">{m['pwl']:,.2f}</td><td style="padding:10px">{m['week_low']:,.2f}</td>
                <td style="padding:10px">{entry}</td><td style="padding:10px;color:#EF4444">{sl}</td>
                <td style="padding:10px;color:#10B981">{t1}</td><td style="padding:10px">{m['target_2']:,.2f}</td>
                <td style="padding:10px">{rr}</td></tr>'''
                mtf_chart_blocks += f'<div style="margin-top:16px"><div style="color:#22D3EE;font-weight:800">{m["name"]} — {status.replace("_"," ")}</div>{chart_html(m,"mtf")}</div>'
            mtf_section_html = f'''<div class="card" style="border:1px solid #06B6D4;box-shadow:0 0 20px rgba(6,182,212,.12)">
            <h2 style="margin-top:0;color:#22D3EE">🔀 INDEX MTF SWEEP → DAILY TRAP → 15-MIN MSS RADAR</h2>
            <div style="color:#94A3B8;font-size:13px;margin-bottom:14px">Index-only BUY-side framework: previous-week low sweep, latest daily close reclaim, then a causal 15-minute market-structure shift after daily confirmation. This section appears only when signals exist.</div>
            <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px;color:#CBD5E1">
            <thead><tr style="background:#1E293B;color:#94A3B8"><th>INDEX</th><th>STATUS</th><th>PWL</th><th>WEEK LOW</th><th>ENTRY/MSS</th><th>SL</th><th>T1</th><th>T2/PWH</th><th>RR</th></tr></thead>
            <tbody>{mtf_rows}</tbody></table></div>{mtf_chart_blocks}</div>'''
        
        # Build Sector HTML Rows
        sector_rows_html = ""
        for s in sector_res.get("all_sectors", []):
            if s["status_code"] == "LEADER":
                badge = '<span style="background:rgba(16,185,129,0.2);color:#10B981;padding:4px 8px;border-radius:6px;font-weight:700;font-size:12px;">🚀 TOP LEADER</span>'
            elif s["status_code"] == "IMPROVING":
                badge = '<span style="background:rgba(59,130,246,0.2);color:#3B82F6;padding:4px 8px;border-radius:6px;font-weight:600;font-size:12px;">📈 IMPROVING</span>'
            elif s["status_code"] == "NEUTRAL":
                badge = '<span style="background:rgba(245,158,11,0.2);color:#F59E0B;padding:4px 8px;border-radius:6px;font-weight:600;font-size:12px;">⚖️ NEUTRAL</span>'
            else:
                badge = '<span style="background:rgba(239,68,68,0.2);color:#EF4444;padding:4px 8px;border-radius:6px;font-weight:600;font-size:12px;">🔻 LAGGARD</span>'
                
            ema_badge = '✅ Above 20 EMA' if s['above_20_ema'] else '❌ Below 20 EMA'
            chg_1w_color = '#10B981' if s['chg_1w'] >= 0 else '#EF4444'
            chg_1m_color = '#10B981' if s['chg_1m'] >= 0 else '#EF4444'
            
            sector_rows_html += f"""
            <tr style="border-bottom: 1px solid #1E293B;">
                <td style="padding: 12px; font-weight: 700; color: #F8FAFC;">{s['name']}</td>
                <td style="padding: 12px; color: #94A3B8; font-size: 13px;">{s['description']}</td>
                <td style="padding: 12px; font-weight: 600; color: {chg_1w_color};">{s['chg_1w']:+.2f}%</td>
                <td style="padding: 12px; font-weight: 600; color: {chg_1m_color};">{s['chg_1m']:+.2f}%</td>
                <td style="padding: 12px; font-size: 13px; color: #CBD5E1;">{ema_badge}</td>
                <td style="padding: 12px; font-weight: 700; color: #38BDF8;">{s['rs_score']:+.2f}</td>
                <td style="padding: 12px;">{badge}</td>
            </tr>
            """

        # Build Daily Index Sweep Engine HTML
        daily_sweep_cards_html = ""
        if daily_sweep_res:
            for sw in daily_sweep_res:
                score = sw.get("quality_score", sw.get("score", 0))
                grade = sw.get("tier_badge", sw.get("grade", "SWEEP"))
                cp = sw.get("current_price", sw.get("close", 0.0))
                dl = sw.get("day_low", 0.0)
                sl = sw.get("swept_level", 0.0)
                wick_pct = sw.get("lower_wick_pct", sw.get("wick_pct", 0.0))
                rsi_val = sw.get("rsi", sw.get("rsi_current", 50.0))
                is_rsi_div = sw.get("rsi_divergence", False)
                has_fvg = sw.get("fvg_detected", False)
                sw_depth = sw.get("sweep_depth_pct", 0.0)
                
                if score >= 70:
                    badge_style = "background: rgba(16, 185, 129, 0.2); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.4);"
                    card_border = "#10B981"
                elif score >= 50:
                    badge_style = "background: rgba(59, 130, 246, 0.2); color: #38BDF8; border: 1px solid rgba(59, 130, 246, 0.4);"
                    card_border = "#38BDF8"
                else:
                    badge_style = "background: rgba(245, 158, 11, 0.2); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.4);"
                    card_border = "#F59E0B"
                    
                confluences_badges = "".join([
                    f'<span style="background: #1E293B; color: #E2E8F0; padding: 3px 8px; border-radius: 4px; font-size: 11.5px; margin-right: 6px; display: inline-block; margin-bottom: 4px;">✓ {c}</span>'
                    for c in sw.get("confluences", [])
                ])
                
                fvg_text = f"Bullish FVG at {sw.get('fvg_bottom', 0):,.1f} - {sw.get('fvg_top', 0):,.1f}" if has_fvg else "No active FVG"
                rsi_text = f"Bullish Divergence (RSI {rsi_val:.1f})" if is_rsi_div else f"RSI Neutral ({rsi_val:.1f})"
                
                daily_sweep_cards_html += f"""
                <div style="background: #030712; border: 1px solid #1E293B; border-left: 4px solid {card_border}; border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">
                        <div>
                            <span style="color: #F8FAFC; font-weight: 800; font-size: 16px;">{sw['name']}</span>
                            <span style="color: #64748B; font-size: 12px; margin-left: 6px;">({sw.get('category', 'Index')})</span>
                        </div>
                        <div>
                            <span style="{badge_style} padding: 4px 10px; border-radius: 20px; font-weight: 800; font-size: 12px;">
                                {grade} ({score}/100)
                            </span>
                        </div>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; font-size: 12.5px; color: #CBD5E1; margin: 10px 0; background: #0B1120; padding: 10px; border-radius: 8px;">
                        <div>Current Close: <strong style="color: #F8FAFC;">{cp:,.2f}</strong></div>
                        <div>Day Low: <strong style="color: #EF4444;">{dl:,.2f}</strong></div>
                        <div>Swept Level: <strong style="color: #F59E0B;">{sl:,.2f}</strong></div>
                        <div>Rejection Wick: <strong style="color: #10B981;">{wick_pct:.1f}%</strong></div>
                    </div>
                    
                    <div style="font-size: 12px; color: #94A3B8; margin-bottom: 8px;">
                        <strong>Reversal Footprints:</strong> {rsi_text} • {fvg_text} • Prior Low Swept by {sw_depth:.2f}% & Reclaimed
                    </div>
                    
                    <div>
                        {confluences_badges}
                    </div>
                    {chart_html(sw,"daily")}
                </div>
                """
        else:
            daily_sweep_cards_html = """
            <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 20px; text-align: center; color: #94A3B8;">
                ⚡ No active daily liquidity sweep setups triggered today. Market trading in standard trend continuation.
            </div>
            """

        # Build Weekly Sweep Engine Section (Friday Edition)
        weekly_section_html = ""
        if is_friday_report:
            weekly_cards_html = ""
            if weekly_sweep_res:
                for wk_hit in weekly_sweep_res:
                    w_score = wk_hit.get("score", 0)
                    w_grade = wk_hit.get("tier_badge", "WEEKLY SWEEP")
                    w_cp = wk_hit.get("current_price", 0.0)
                    w_low = wk_hit.get("weekly_low", 0.0)
                    w_sl = wk_hit.get("swept_level", 0.0)
                    w_pool = wk_hit.get("pool_type", "Swing Low")
                    w_wick = wk_hit.get("wick_pct", 0.0)
                    w_sl_target = wk_hit.get("stop_loss_level", 0.0)
                    
                    if w_score >= 70:
                        w_badge_style = "background: rgba(16, 185, 129, 0.2); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.4);"
                        w_border = "#10B981"
                    elif w_score >= 50:
                        w_badge_style = "background: rgba(56, 189, 248, 0.2); color: #38BDF8; border: 1px solid rgba(56, 189, 248, 0.4);"
                        w_border = "#38BDF8"
                    else:
                        w_badge_style = "background: rgba(245, 158, 11, 0.2); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.4);"
                        w_border = "#F59E0B"
                        
                    w_confluences_badges = "".join([
                        f'<span style="background: #1E293B; color: #E2E8F0; padding: 3px 8px; border-radius: 4px; font-size: 11.5px; margin-right: 6px; display: inline-block; margin-bottom: 4px;">✓ {c}</span>'
                        for c in wk_hit.get("confluences", [])
                    ])
                    
                    weekly_cards_html += f"""
                    <div style="background: #030712; border: 1px solid #1E293B; border-left: 4px solid {w_border}; border-radius: 12px; padding: 16px; margin-bottom: 14px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <span style="color: #F8FAFC; font-weight: 800; font-size: 16px;">{wk_hit['name']}</span>
                                <span style="color: #64748B; font-size: 12px; margin-left: 6px;">({wk_hit.get('category', 'Index')})</span>
                            </div>
                            <div>
                                <span style="{w_badge_style} padding: 4px 10px; border-radius: 20px; font-weight: 800; font-size: 12px;">
                                    {w_grade} ({w_score}/100)
                                </span>
                            </div>
                        </div>
                        
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; font-size: 12.5px; color: #CBD5E1; margin: 10px 0; background: #0B1120; padding: 10px; border-radius: 8px;">
                            <div>Weekly Close: <strong style="color: #F8FAFC;">{w_cp:,.2f}</strong></div>
                            <div>Weekly Low: <strong style="color: #EF4444;">{w_low:,.2f}</strong></div>
                            <div>Swept {w_pool}: <strong style="color: #F59E0B;">{w_sl:,.2f}</strong></div>
                            <div>Weekly Lower Wick: <strong style="color: #10B981;">{w_wick:.1f}%</strong></div>
                        </div>
                        
                        <div style="font-size: 12px; color: #94A3B8; margin-bottom: 8px;">
                            <strong>Positional Swing Strategy:</strong> Target 2 to 6 Weeks Holding • Invalidation Stop Loss below Weekly Wick at <strong style="color: #F8FAFC;">{w_sl_target:,.2f}</strong>.
                        </div>
                        
                        <div>
                            {w_confluences_badges}
                        </div>
                        {chart_html(wk_hit,"weekly")}
                    </div>
                    """
            else:
                weekly_cards_html = """
                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 20px; text-align: center; color: #94A3B8;">
                    ⚡ No multi-week fractal liquidity sweeps triggered this week across NSE indices. Standard weekly trend intact.
                </div>
                """
                
            weekly_section_html = f"""
            <!-- FRIDAY SPECIAL: WEEKLY INDEX LIQUIDITY SWEEP RADAR -->
            <div class="card" style="border: 1px solid #8B5CF6; box-shadow: 0 0 20px rgba(139, 92, 246, 0.15);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">
                    <h2 style="margin: 0; font-size: 20px; color: #A78BFA; display: flex; align-items: center; gap: 8px;">
                        🗓️ FRIDAY SPECIAL: NSE INDEX WEEKLY LIQUIDITY SWEEP RADAR
                    </h2>
                    <span style="background: rgba(139, 92, 246, 0.2); color: #C4B5FD; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase;">
                        Multi-Week Positional Horizon (2-6 Weeks)
                    </span>
                </div>
                <div style="color: #94A3B8; font-size: 13px; margin-bottom: 16px;">
                    Weekly Fractal Liquidity Sweeps, 26W / 52W Low Absorption Hammers, and Weekly Trend Reversals across all NSE Broad Market, Sectoral & Thematic Indices. <em>(Delivered weekly on Friday EOD)</em>.
                </div>
                {weekly_cards_html}
            </div>
            """
        else:
            weekly_section_html = f"""
            <!-- WEEKLY SWEEP NOTICE -->
            <div style="background: rgba(15, 23, 42, 0.6); border: 1px dashed #334155; border-radius: 12px; padding: 14px 18px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <div style="color: #94A3B8; font-size: 13px;">
                    🗓️ <strong>Weekly Index Sweep Radar</strong>: Runs automatically every <strong>Friday at 9:00 PM IST</strong> with the weekly candle close to deliver 2-to-6 week positional swing setups.
                </div>
                <span style="background: #1E293B; color: #94A3B8; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                    Friday Routine Active
                </span>
            </div>
            """

        # Build Sheet Tables HTML
        sheet_sections_html = ""
        for sec_name, rows in calc_res["sheet_sections"].items():
            rows_html = ""
            for r in rows:
                p_name = r["participant"]
                l_action = r["long_action"]
                s_action = r["short_action"]
                n_action = r["net_action"]
                c_today = f"{r['carried_t0']:,}"
                c_1d = f"{r['carried_t1']:,}"
                c_2d = f"{r['carried_t2']:,}"
                
                net_color = "#10B981" if r["sentiment"] == "BULLISH" else "#EF4444" if r["sentiment"] == "BEARISH" else "#94A3B8"
                car_color = "#10B981" if r["carried_sentiment"] == "BULLISH" else "#EF4444" if r["carried_sentiment"] == "BEARISH" else "#94A3B8"
                
                rows_html += f"""
                <tr style="border-bottom: 1px solid #1E293B; font-size: 13px;">
                    <td style="padding: 8px 12px; font-weight: 700; color: #E2E8F0;">{p_name}</td>
                    <td style="padding: 8px 12px; color: #CBD5E1;">{l_action}</td>
                    <td style="padding: 8px 12px; color: #CBD5E1;">{s_action}</td>
                    <td style="padding: 8px 12px; font-weight: 700; color: {net_color};">{n_action}</td>
                    <td style="padding: 8px 12px; font-weight: 700; color: {car_color};">{c_today}</td>
                    <td style="padding: 8px 12px; color: #94A3B8;">{c_1d}</td>
                    <td style="padding: 8px 12px; color: #64748B;">{c_2d}</td>
                </tr>
                """
                
            sheet_sections_html += f"""
            <div style="background: #0F172A; border-radius: 12px; border: 1px solid #1E293B; margin-bottom: 20px; overflow: hidden;">
                <div style="background: #1E293B; padding: 10px 16px; font-weight: 800; color: #38BDF8; font-size: 15px; letter-spacing: 0.5px;">
                    📊 {sec_name.upper()}
                </div>
                <table style="width: 100%; border-collapse: collapse; text-align: left;">
                    <thead>
                        <tr style="background: #0B1120; color: #94A3B8; font-size: 12px; text-transform: uppercase;">
                            <th style="padding: 10px 12px;">Participant</th>
                            <th style="padding: 10px 12px;">Long Delta</th>
                            <th style="padding: 10px 12px;">Short Delta</th>
                            <th style="padding: 10px 12px;">Net Today</th>
                            <th style="padding: 10px 12px;">Carried (Today)</th>
                            <th style="padding: 10px 12px;">1 Day Ago</th>
                            <th style="padding: 10px 12px;">2 Days Ago</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
            """

        # Traps HTML
        traps_html = ""
        for trap in calc_res.get("traps", []):
            traps_html += f"""
            <div style="background: rgba(15, 23, 42, 0.8); border-left: 4px solid {trap['color']}; padding: 14px 18px; border-radius: 8px; margin-bottom: 12px; border: 1px solid #1E293B;">
                <div style="font-weight: 800; color: {trap['color']}; font-size: 15px; margin-bottom: 4px;">{trap['title']}</div>
                <div style="color: #CBD5E1; font-size: 13.5px; line-height: 1.5;">{trap['description']}</div>
            </div>
            """
        if not traps_html:
            traps_html = '<div style="color:#94A3B8;font-size:13px;padding:10px;">No extreme trapping divergence detected today. Market trading in structural alignment.</div>'

        # Macro Cards HTML
        macro_cards_html = ""
        if macro_res:
            m_items = [
                ("Brent Crude", macro_res.get("brent_crude", {}), "USD/bbl", "<$85 is Bullish"),
                ("US 10Y Yield", macro_res.get("us_10y_yield", {}), "%", "<4.4% is Bullish"),
                ("Dollar Index (DXY)", macro_res.get("us_dollar_index", {}), "pts", "<102 is Bullish"),
                ("Dow Jones", macro_res.get("dow_jones", {}), "pts", "US Sentiment"),
                ("Nifty 50 Index", macro_res.get("nifty_50", {}), "pts", "Domestic Benchmark"),
            ]
            for label, data, unit, note in m_items:
                chg = data.get("change_pct", 0)
                px = data.get("current", 0)
                chg_c = "#10B981" if chg >= 0 else "#EF4444"
                macro_cards_html += f"""
                <div style="background: #0F172A; border: 1px solid #1E293B; border-radius: 10px; padding: 12px 16px; flex: 1; min-width: 140px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 600;">{label}</div>
                    <div style="color: #F8FAFC; font-size: 18px; font-weight: 800; margin: 4px 0;">{px:,.2f} <span style="font-size: 12px; color: #64748B;">{unit}</span></div>
                    <div style="font-size: 12px; font-weight: 700; color: {chg_c};">{chg:+.2f}% <span style="font-size: 11px; color: #64748B; font-weight: 400;">({note})</span></div>
                </div>
                """

        # Full HTML Template
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Money Institutional Prediction Report - {display_date}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #030712;
            color: #F8FAFC;
            margin: 0;
            padding: 24px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .card {{
            background: #0B1120;
            border: 1px solid #1E293B;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .btn-badge {{
            display: inline-block;
            padding: 8px 18px;
            border-radius: 30px;
            font-weight: 800;
            font-size: 16px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER HERO BANNER -->
        <div class="card" style="background: linear-gradient(135deg, #0B1120 0%, #111827 50%, #0F172A 100%); border-top: 4px solid #38BDF8;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; margin-bottom: 16px;">
                <div>
                    <span style="background: rgba(56, 189, 248, 0.15); color: #38BDF8; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase;">
                        Institutional Intelligence Report {'• 🗓️ Friday Edition' if is_friday_report else ''}
                    </span>
                    <h1 style="margin: 8px 0 4px 0; font-size: 28px; font-weight: 900; color: #FFFFFF;">
                        Smart Money Daily Market Prediction
                    </h1>
                    <div style="color: #94A3B8; font-size: 14px;">
                        Date: <strong style="color: #E2E8F0;">{display_date}</strong> | Official NSE Participant Open Interest & Quantitative Analytics
                    </div>
                </div>
                <div>
                    <div class="btn-badge" style="background: {signal_color}; color: #FFFFFF; box-shadow: 0 4px 14px rgba(0,0,0,0.4);">
                        {signal}
                    </div>
                </div>
            </div>

            <!-- REGIME & SCORE HERO GRID -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 20px;">
                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 16px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 600; text-transform: uppercase;">Composite Institutional Score (CIS)</div>
                    <div style="font-size: 32px; font-weight: 900; color: {'#10B981' if cis >= 3 else '#EF4444' if cis <= -3 else '#F59E0B'}; margin: 4px 0;">
                        {cis:+.1f} <span style="font-size: 14px; color: #64748B;">/ 10</span>
                    </div>
                    <div style="color: #CBD5E1; font-size: 12.5px;">
                        {'🟢 High Bullish Conviction' if cis >= 4 else '🔴 High Bearish Pressure' if cis <= -4 else '🟡 Range-Bound / Neutral'}
                    </div>
                </div>

                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 16px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 600; text-transform: uppercase;">Market Regime</div>
                    <div style="font-size: 18px; font-weight: 800; color: {regime_res['regime_color']}; margin: 8px 0;">
                        {regime_name}
                    </div>
                    <div style="color: #94A3B8; font-size: 12px; line-height: 1.4;">
                        FII Index Long Ratio: <strong style="color: #F8FAFC;">{fii_ratio}%</strong>
                    </div>
                </div>

                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 16px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 600; text-transform: uppercase;">Capital Allocation %</div>
                    <div style="display: flex; gap: 12px; align-items: baseline; margin: 6px 0;">
                        <span style="font-size: 26px; font-weight: 900; color: #10B981;">{cap_pct}% <span style="font-size: 12px; color: #94A3B8;">Stocks</span></span>
                        <span style="font-size: 20px; font-weight: 800; color: #F59E0B;">{cash_pct}% <span style="font-size: 12px; color: #94A3B8;">Cash</span></span>
                    </div>
                    <div style="color: #CBD5E1; font-size: 12px;">
                        Exposure level recommended for 10-40 day swings.
                    </div>
                </div>

                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 16px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 600; text-transform: uppercase;">FII 3-Day Stock Flow</div>
                    <div style="font-size: 24px; font-weight: 900; color: {'#10B981' if fii_stk_3d > 0 else '#EF4444'}; margin: 6px 0;">
                        {fii_stk_3d:+,}
                    </div>
                    <div style="color: #94A3B8; font-size: 12px;">
                        {'Institutional Stock Accumulation' if fii_stk_3d > 0 else 'Institutional Stock Distribution'}
                    </div>
                </div>
            </div>
        </div>

        <!-- ACTIONABLE SWING STRATEGY & NIFTY TRAJECTORY -->
        <div class="card">
            <h2 style="margin-top: 0; font-size: 20px; color: #38BDF8; display: flex; align-items: center; gap: 8px;">
                🎯 10-TO-40 DAY SWING STRATEGY & CHART TRAJECTORY
            </h2>
            
            <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 18px; margin-bottom: 16px;">
                <div style="color: #F8FAFC; font-weight: 700; font-size: 15px; margin-bottom: 6px;">Actionable Protocol:</div>
                <div style="color: #CBD5E1; font-size: 14px; line-height: 1.6;">
                    {action_text}
                </div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 16px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">Expected Trajectory Curve</div>
                    <div style="color: #38BDF8; font-size: 14px; font-weight: 600; line-height: 1.5;">
                        {regime_res['trajectory']}
                    </div>
                </div>

                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 16px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">Key Technical & Sweep Levels</div>
                    <div style="font-size: 13.5px; color: #CBD5E1; line-height: 1.8;">
                        <div>🛑 Resistance 2: <strong style="color: #F8FAFC;">{regime_res['resistance_2']}</strong></div>
                        <div>🚧 Resistance 1: <strong style="color: #F8FAFC;">{regime_res['resistance_1']}</strong></div>
                        <div>🛡️ Support 1: <strong style="color: #10B981;">{regime_res['support_1']}</strong></div>
                        <div>⚠️ SL Sweep Zone: <strong style="color: #F59E0B;">{regime_res['sweep_zone']}</strong> (Liquidity Hunt)</div>
                        <div>⛔ Support 2: <strong style="color: #EF4444;">{regime_res['support_2']}</strong></div>
                    </div>
                </div>
            </div>
        </div>

        {scenario_lab_html}

        {weekly_section_html}

        {mtf_section_html}

        <!-- DAILY NSE INDEX LIQUIDITY SWEEP & CONFLUENCE RADAR -->
        <div class="card">
            <h2 style="margin-top: 0; font-size: 20px; color: #F43F5E; display: flex; align-items: center; gap: 8px;">
                🎯 NSE INDEX DAILY LIQUIDITY SWEEP & REVERSAL RADAR
            </h2>
            <div style="color: #94A3B8; font-size: 13px; margin-bottom: 16px;">
                Daily multi-confluence screening across Broad Market, Sectoral & Thematic NSE Indices detecting Stop-Loss Sweeps, Hammer Rejection Wicks, Bullish RSI Divergences, and Fair Value Gaps (FVGs). <em>(Runs every day)</em>.
            </div>
            {daily_sweep_cards_html}
        </div>

        <!-- INSTITUTIONAL TRAPS & SETUP DETECTION -->
        <div class="card">
            <h2 style="margin-top: 0; font-size: 20px; color: #F59E0B; display: flex; align-items: center; gap: 8px;">
                ⚡ SMART MONEY TRAP DETECTION & MARKET FOOTPRINTS
            </h2>
            {traps_html}
        </div>

        <!-- SECTOR ROTATION LEADERBOARD -->
        <div class="card">
            <h2 style="margin-top: 0; font-size: 20px; color: #10B981; display: flex; align-items: center; gap: 8px;">
                🔄 INSTITUTIONAL SECTOR ROTATION LEADERBOARD
            </h2>
            <div style="color: #94A3B8; font-size: 13px; margin-bottom: 16px;">
                {sector_res.get('rotation_summary', '')}
            </div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; text-align: left;">
                    <thead>
                        <tr style="background: #1E293B; color: #94A3B8; font-size: 12px; text-transform: uppercase;">
                            <th style="padding: 10px 12px;">Sector Name</th>
                            <th style="padding: 10px 12px;">Constituents</th>
                            <th style="padding: 10px 12px;">1-Week %</th>
                            <th style="padding: 10px 12px;">1-Month %</th>
                            <th style="padding: 10px 12px;">20 EMA Status</th>
                            <th style="padding: 10px 12px;">RS Score vs Nifty</th>
                            <th style="padding: 10px 12px;">Institutional Stance</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sector_rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- GLOBAL MACRO MATRIX -->
        <div class="card">
            <h2 style="margin-top: 0; font-size: 20px; color: #38BDF8; display: flex; align-items: center; gap: 8px;">
                🌐 GLOBAL MACRO MATRIX
            </h2>
            <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px;">
                {macro_cards_html}
            </div>
        </div>

        <!-- AMIT DHAMIJA EXCEL SHEET SECTION TABLES -->
        <div class="card">
            <h2 style="margin-top: 0; font-size: 20px; color: #E2E8F0; display: flex; align-items: center; gap: 8px;">
                📋 COMPLETE PARTICIPANT OPEN INTEREST MATRIX
            </h2>
            <div style="color: #94A3B8; font-size: 13px; margin-bottom: 16px;">
                Detailed breakdown across Index Futures, Calls, Puts, Stock Futures, Stock Calls, and Stock Puts.
            </div>
            {sheet_sections_html}
        </div>

        <!-- FOOTER -->
        <div style="text-align: center; color: #64748B; font-size: 12px; padding: 16px 0;">
            Smart Money Institutional Prediction System • Built for 10-40 Day Positional & Swing Traders • Zero Paid Subscriptions
        </div>
    </div>
</body>
</html>
"""
        # Save HTML file
        out_html_path = os.path.join(self.output_dir, f"prediction_report_{date_str}.html")
        latest_html_path = os.path.join(self.output_dir, "latest_prediction_report.html")
        
        with open(out_html_path, "w", encoding="utf-8") as f:
            f.write(html)
        with open(latest_html_path, "w", encoding="utf-8") as f:
            f.write(html)
            
        # Also generate Markdown Report
        md = self._generate_markdown(
            calc_res, regime_res, sector_res, macro_res, daily_sweep_res,
            weekly_sweep_res, mtf_res, scenario_lab_data
        )
        out_md_path = os.path.join(self.output_dir, f"prediction_report_{date_str}.md")
        latest_md_path = os.path.join(self.output_dir, "latest_prediction_report.md")
        
        with open(out_md_path, "w", encoding="utf-8") as f:
            f.write(md)
        with open(latest_md_path, "w", encoding="utf-8") as f:
            f.write(md)
            
        return {
            "html_path": out_html_path,
            "latest_html_path": latest_html_path,
            "md_path": out_md_path,
            "latest_md_path": latest_md_path,
            "html_content": html
        }

    def _generate_markdown(
        self, calc_res, regime_res, sector_res, macro_res,
        daily_sweep_res=None, weekly_sweep_res=None, mtf_res=None,
        scenario_lab_data=None,
    ):
        display_date = calc_res["display_date"]
        cis = calc_res["cis_score"]
        fii_ratio = calc_res["fii_long_ratio"]
        fii_stk_3d = calc_res["fii_stk_flow_3d"]
        signal = regime_res["primary_signal"]
        daily_sweep_res = daily_sweep_res or []
        is_friday_report = weekly_sweep_res is not None
        
        md = f"""# 🏛️ Smart Money Institutional Prediction Report — {display_date} {'(🗓️ Friday Edition)' if is_friday_report else ''}

**Primary Signal**: `{signal}`
**Market Regime**: `{regime_res['regime_name']}`
**Composite Score (CIS)**: `{cis:+.1f} / 10`
**FII Index Long Ratio**: `{fii_ratio}%`
**FII 3-Day Stock Futures Flow**: `{fii_stk_3d:+,} contracts`
**Capital Allocation**: `{regime_res['capital_allocation_pct']}% Stocks | {regime_res['cash_reserve_pct']}% Cash`

---

## 🎯 10-to-40 Day Swing Protocol
{regime_res['action_instructions']}

### Expected Chart Trajectory
{regime_res['trajectory']}

### Key Institutional Levels
- **Resistance 2**: `{regime_res['resistance_2']}`
- **Resistance 1**: `{regime_res['resistance_1']}`
- **Support 1**: `{regime_res['support_1']}`
- **SL Sweep Zone (Liquidity Hunt)**: `{regime_res['sweep_zone']}`
- **Support 2**: `{regime_res['support_2']}`
"""
        md += render_scenario_lab_markdown(scenario_lab_data, calc_res.get("date"))
        mtf_res = mtf_res or {"has_signals": False, "actionable": []}
        if mtf_res.get("has_signals"):
            md += """
---

## 🔀 Index MTF Sweep → Daily Trap → 15-Min MSS Radar
*Signal-only section; individual stocks are never scanned.*

| Index | Status | PWL | Week Low | Entry/MSS | SL | T1 | T2/PWH | RR |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
"""
            for m in mtf_res.get("actionable", []):
                md += f"| {m['name']} | {m.get('status','')} | {m.get('pwl','—')} | {m.get('week_low','—')} | {m.get('entry') or 'Waiting'} | {m.get('stoploss') or '—'} | {m.get('target_1') or '—'} | {m.get('target_2') or '—'} | {m.get('rr_t2') or '—'} |\n"

        if is_friday_report:
            md += """
---

## 🗓️ FRIDAY SPECIAL: NSE Index Weekly Liquidity Sweep Radar (Multi-Week Positional)
Weekly Fractal Liquidity Sweeps, 26W / 52W Low Absorption Hammers, and Weekly Trend Reversals across all NSE Broad Market, Sectoral & Thematic Indices *(Delivered every Friday)*.

| Index Name | Category | Grade & Score | Weekly Close | Weekly Low | Swept Support | Wick % | Invalidation SL | Confluences |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
            if weekly_sweep_res:
                for wk in weekly_sweep_res:
                    w_confs = ", ".join(wk.get("confluences", [])[:2])
                    md += f"| {wk['name']} | {wk.get('category', 'Index')} | {wk.get('tier_badge', 'WEEKLY')} ({wk.get('score', 0)}/100) | {wk.get('current_price', 0):,.1f} | {wk.get('weekly_low', 0):,.1f} | {wk.get('swept_level', 0):,.1f} ({wk.get('pool_type', 'Low')}) | {wk.get('wick_pct', 0):.1f}% | {wk.get('stop_loss_level', 0):,.1f} | {w_confs} |\n"
            else:
                md += "| *No multi-week index sweep triggers detected this week* | - | - | - | - | - | - | - | - |\n"

        md += f"""
---

## 🎯 NSE Index Daily Liquidity Sweep Radar (Daily Routine)
Daily multi-confluence screening across Broad Market, Sectoral & Thematic NSE Indices detecting Stop-Loss Sweeps, Hammer Rejection Wicks, RSI Divergences, and FVGs.

| Index Name | Category | Grade & Score | Close | Day Low | Swept Support | Wick % | RSI Divergence | Confluences |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
        for sw in daily_sweep_res:
            rsi_d = "Bullish Div" if sw.get('rsi_divergence', False) else "Neutral"
            confs = ", ".join(sw.get('confluences', [])[:2])
            cp = sw.get("current_price", sw.get("close", 0.0))
            dl = sw.get("day_low", 0.0)
            sl = sw.get("swept_level", 0.0)
            wick_pct = sw.get("lower_wick_pct", sw.get("wick_pct", 0.0))
            score = sw.get("quality_score", sw.get("score", 0))
            grade = sw.get("tier_badge", sw.get("grade", "SWEEP"))
            md += f"| {sw['name']} | {sw.get('category', 'Index')} | {grade} ({score}/100) | {cp:,.1f} | {dl:,.1f} | {sl:,.1f} | {wick_pct:.1f}% | {rsi_d} | {confs} |\n"
            
        if not daily_sweep_res:
            md += "| *No active daily index sweep triggers detected today* | - | - | - | - | - | - | - | - |\n"

        md += f"""
---

## 🔄 Sector Rotation Ranking
{sector_res.get('rotation_summary', '')}

| Sector Name | 1-Week % | 1-Month % | 20 EMA Status | RS Score | Institutional Stance |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
        for s in sector_res.get("all_sectors", []):
            ema_str = "Above 20 EMA" if s["above_20_ema"] else "Below 20 EMA"
            md += f"| {s['name']} | {s['chg_1w']:+.2f}% | {s['chg_1m']:+.2f}% | {ema_str} | {s['rs_score']:+.2f} | {s['status']} |\n"
            
        md += "\n---\n\n## ⚡ Smart Money Traps Detected\n"
        for t in calc_res.get("traps", []):
            md += f"- **{t['title']}**: {t['description']}\n"
        if not calc_res.get("traps"):
            md += "- *No extreme retail trapping divergence detected today.*\n"
            
        return md
