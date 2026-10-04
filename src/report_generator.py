import os
import datetime
from html import escape
from signal_chart_renderer import chart_html


def _format_pct(value, signed=False):
    if value is None:
        return "—"
    value = float(value)
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def _format_probability(value):
    return f"{float(value) * 100:.1f}%"


class ReportGenerator:
    def __init__(self, output_dir="reports"):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.output_dir = os.path.join(self.base_dir, output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def _normalize_weekly_scan(result):
        """Accept both the old hit-list API and the newer full scan diagnostics."""
        if result is None:
            return None
        if isinstance(result, dict):
            normalized = dict(result)
            normalized["weekly_hits"] = list(result.get("weekly_hits") or [])
            normalized["near_misses"] = list(result.get("near_misses") or [])
            normalized["failed_indices"] = list(result.get("failed_indices") or [])
            if normalized.get("total_scanned") is not None:
                normalized.setdefault(
                    "scanned_indices",
                    max(int(normalized["total_scanned"]) - len(normalized["failed_indices"]), 0),
                )
            return normalized
        return {
            "weekly_hits": list(result),
            "near_misses": [],
            "failed_indices": [],
            "total_scanned": None,
            "scanned_indices": None,
            "scan_date": None,
            "is_friday": True,
        }

    @staticmethod
    def _normalize_daily_scan(result):
        """Accept a detailed daily scan or the historical list-only result."""
        if result is None:
            return {"setups": [], "total_indices": None, "scanned_indices": None, "failed_indices": [], "status": "unknown"}
        if isinstance(result, dict):
            normalized = dict(result)
            normalized["setups"] = list(result.get("setups") or [])
            normalized["failed_indices"] = list(result.get("failed_indices") or [])
            return normalized
        return {"setups": list(result), "total_indices": None, "scanned_indices": None, "failed_indices": [], "status": "unknown"}

    @staticmethod
    def _daily_coverage_text(scan):
        total, scanned = scan.get("total_indices"), scan.get("scanned_indices")
        failed = scan.get("failed_indices", [])
        if total is None or scanned is None:
            return "feed coverage not recorded"
        if int(scanned) == 0:
            result = f"NO CONCLUSION — 0/{int(total)} feeds usable"
        elif failed:
            result = f"PARTIAL — {int(scanned)}/{int(total)} feeds usable; {len(failed)} failed"
        else:
            result = f"FULL — {int(scanned)}/{int(total)} feeds usable"
        if failed:
            result += "; failed: " + ", ".join(str(name).replace("|", "\\|") for name in failed)
        return result

    @staticmethod
    def _daily_coverage_html(scan):
        total, scanned = scan.get("total_indices"), scan.get("scanned_indices")
        failed = scan.get("failed_indices", [])
        if total is None or scanned is None:
            result = "Daily index-feed coverage was not recorded by this scan."
        elif int(scanned) == 0:
            result = f"⚠️ No conclusion: 0/{int(total)} daily index feeds returned valid, recent history."
        elif failed:
            result = f"⚠️ Partial daily scan: {int(scanned)}/{int(total)} feeds usable; {len(failed)} failed."
        else:
            result = f"✅ Full daily scan: {int(scanned)}/{int(total)} feeds usable."
        if failed:
            names = ", ".join(escape(str(name)) for name in failed[:8])
            if len(failed) > 8:
                names += f" and {len(failed) - 8} more"
            result += f" Failed feeds: {names}."
        return result

    @staticmethod
    def _sector_coverage_text(sector_res):
        coverage = (sector_res or {}).get("feed_coverage")
        if not coverage:
            return ""
        total = coverage.get("total_indices")
        scanned = coverage.get("scanned_indices")
        status = coverage.get("status", "unknown")
        if total is None or scanned is None:
            summary = "Sector index-feed coverage was not recorded."
        elif status == "unavailable" or int(scanned) == 0:
            summary = f"NO CONCLUSION — 0/{int(total)} sector histories usable."
        elif status == "partial":
            summary = f"PARTIAL — {int(scanned)}/{int(total)} sector histories usable."
        else:
            summary = f"FULL — {int(scanned)}/{int(total)} sector histories usable."
        failed = coverage.get("failed_indices", [])
        if failed:
            names = ", ".join(str(name).replace("|", "\\|") for name in failed[:8])
            if len(failed) > 8:
                names += f" and {len(failed) - 8} more"
            summary += f" Failed sectors: {names}."
        details = coverage.get("errors", [])
        if details:
            messages = [
                f"{row.get('name', 'feed')}: {row.get('reason', 'unavailable')}"
                for row in details[:3] if isinstance(row, dict)
            ]
            if messages:
                summary += " Feed details: " + "; ".join(messages)
                if len(details) > 3:
                    summary += f"; and {len(details) - 3} more"
                summary += "."
        return summary

    def _scenario_section_html(self, scenario_res):
        if not scenario_res or not scenario_res.get("available"):
            reason = (scenario_res or {}).get("error", "Live NIFTY/VIX history was not available.")
            snapshot = (scenario_res or {}).get("model_snapshot_as_of")
            snapshot_note = f" Model reference snapshot: {escape(str(snapshot))}." if snapshot else ""
            return f"""
            <div class="card" id="nifty-scenario-overlay" style="border:1px solid #F59E0B;">
                <h2 style="margin-top:0;color:#FBBF24">🧭 NIFTY SCENARIO LAB — 1–3 MONTH CONTEXT</h2>
                <div style="color:#CBD5E1">Scenario overlay unavailable: {escape(str(reason))}.{snapshot_note}</div>
                <div style="color:#94A3B8;font-size:12px;margin-top:8px">The core Smart Money 10–40 day report is unaffected. No old embedded forecast is substituted for missing live data.</div>
            </div>
            """

        inputs = scenario_res.get("inputs", {})
        probs = scenario_res.get("probabilities", {})
        confidence = scenario_res.get("confidence_bucket", {})
        accuracy = scenario_res.get("accuracy", {})
        composite = scenario_res.get("composite", {})
        metric_specs = [
            ("y_up_1M", "NIFTY higher in 1 month", "#38BDF8"),
            ("y_up_3M", "NIFTY higher in 3 months", "#A78BFA"),
            ("y_dip5_3M", "3M risk of 5%+ dip", "#F87171"),
            ("y_rally5_3M", "3M chance of 5%+ rally", "#34D399"),
        ]
        metric_cards = ""
        for key, label, color in metric_specs:
            record = probs.get(key, {})
            probability = record.get("calibrated")
            metric_cards += f"""
            <div style="background:#030712;border:1px solid #1E293B;border-radius:10px;padding:13px;min-width:160px;flex:1">
                <div style="font-size:11px;color:#94A3B8;text-transform:uppercase;font-weight:700">{label}</div>
                <div style="font-size:25px;font-weight:900;color:{color};margin:4px 0">{_format_probability(probability) if probability is not None else '—'}</div>
                <div style="font-size:11px;color:#94A3B8">Historical base rate: {_format_pct(record.get('base_rate_pct'))}</div>
            </div>
            """

        input_values = [
            ("NIFTY 50", f"{float(inputs.get('nifty', 0)):,.2f}"),
            ("India VIX", f"{float(inputs.get('india_vix', 0)):.2f} ({float(inputs.get('india_vix_pct', 0)):.1f}th pct)"),
            ("US VIX (1-session lag)", f"{float(inputs.get('us_vix', 0)):.2f} ({float(inputs.get('us_vix_pct', 0)):.1f}th pct)"),
            ("RSI-14", f"{float(inputs.get('rsi14', 0)):.1f}"),
            ("Distance from 200 EMA", _format_pct(inputs.get("dist200"), signed=True)),
            ("Drawdown from 52-week high", _format_pct(inputs.get("dd252"), signed=True)),
            ("Distance above 6-month low", _format_pct(inputs.get("dist6mlow"), signed=True)),
            ("Bullish strength atoms", f"{int(inputs.get('bull_count', 0))}/7"),
        ]
        input_cells = "".join(
            f'<div style="padding:7px 10px;background:#030712;border-radius:7px;color:#CBD5E1"><span style="color:#94A3B8">{escape(label)}:</span> <strong>{escape(value)}</strong></div>'
            for label, value in input_values
        )

        scenario_cards = ""
        for row in scenario_res.get("matched_scenarios", []):
            one_month = row.get("one_month", {})
            three_month = row.get("three_month", {})
            historical_action = row.get("historical_action", "")
            scenario_cards += f"""
            <div style="background:#030712;border:1px solid #1E293B;border-left:3px solid #A78BFA;border-radius:9px;padding:13px;margin:9px 0">
                <div style="font-weight:800;color:#F8FAFC">{escape(str(row.get('name', row.get('key', 'Scenario'))))}</div>
                <div style="font-size:12px;color:#94A3B8;margin:4px 0">{escape(str(row.get('meaning', '')))}</div>
                <div style="font-size:12px;color:#CBD5E1">1M median {_format_pct(one_month.get('med'), signed=True)} / historically up {_format_pct(one_month.get('up%'))} · 3M median {_format_pct(three_month.get('med'), signed=True)} / historically up {_format_pct(three_month.get('up%'))} · 3M observations n={int(three_month.get('n', 0))}</div>
                <div style="font-size:11px;color:#94A3B8;margin-top:3px">Rule: {escape(str(row.get('rule', '')))}</div>
                {f'<div style="font-size:11px;color:#FBBF24;margin-top:4px">Source playbook context (historical, not a current instruction): {escape(str(historical_action))}</div>' if historical_action else ''}
            </div>
            """
        if not scenario_cards:
            scenario_cards = '<div style="color:#94A3B8;padding:10px 0">No named historical scenario matched the latest feature set.</div>'

        forecast_rows = ""
        if composite:
            forecast_rows = f"""
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:9px;margin-top:10px">
                <div style="background:#030712;padding:12px;border-radius:8px;color:#CBD5E1">1M blended median context<br><strong style="color:#38BDF8">{_format_pct(composite.get('one_month_median_pct'), signed=True)} → {float(composite.get('one_month_level', 0)):,.0f}</strong></div>
                <div style="background:#030712;padding:12px;border-radius:8px;color:#CBD5E1">3M blended median context<br><strong style="color:#A78BFA">{_format_pct(composite.get('three_month_median_pct'), signed=True)} → {float(composite.get('three_month_level', 0)):,.0f}</strong></div>
                <div style="background:#030712;padding:12px;border-radius:8px;color:#CBD5E1">Matched-scenario typical 3M dip<br><strong style="color:#F87171">{_format_pct(composite.get('typical_dip_3m_pct'), signed=True)}{f' → {float(composite["typical_dip_level"]):,.0f}' if composite.get('typical_dip_level') is not None else ''}</strong></div>
                <div style="background:#030712;padding:12px;border-radius:8px;color:#CBD5E1">Matched-scenario typical 3M rally<br><strong style="color:#34D399">{_format_pct(composite.get('typical_rally_3m_pct'), signed=True)}{f' → {float(composite["typical_rally_level"]):,.0f}' if composite.get('typical_rally_level') is not None else ''}</strong></div>
            </div>
            <div style="font-size:11px;color:#64748B;margin-top:6px">Estimate method: {escape(str(composite.get('estimate_method', 'model/scenario blend')))}. Illustrative context only, not a price target or stop level.</div>
            """

        bucket = confidence.get("bucket", "—")
        q_count = confidence.get("n", "—")
        snapshot = scenario_res.get("model_snapshot_as_of", "unknown")
        as_of = scenario_res.get("as_of", "unknown")
        direction_note = (
            f"Walk-forward record ({escape(str(accuracy.get('oos_window', '')))}): NIFTY 1M direction {accuracy.get('nifty_dir_1M', '—')}% vs {accuracy.get('nifty_base_1M', '—')}% base rate (AUC {accuracy.get('dir1M_auc', '—')}); "
            f"3M direction {accuracy.get('nifty_dir_3M', '—')}% vs {accuracy.get('nifty_base_3M', '—')}% base rate (AUC {accuracy.get('dir3M_auc', '—')})."
        )
        calibration_note = escape(str(accuracy.get("calibration_note", "")))
        return f"""
        <div class="card" id="nifty-scenario-overlay" style="border:1px solid #7C3AED;box-shadow:0 0 18px rgba(124,58,237,.12)">
            <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;flex-wrap:wrap">
                <div>
                    <h2 style="margin:0;color:#C4B5FD">🧭 NIFTY SCENARIO LAB — 1–3 MONTH MARKET CONTEXT</h2>
                    <div style="color:#94A3B8;font-size:12px;margin-top:4px">Fresh market inputs as of {escape(str(as_of))} · Model/statistics snapshot {escape(str(snapshot))}</div>
                </div>
                <span style="background:#2E1065;color:#DDD6FE;border-radius:20px;padding:4px 10px;font-size:11px;font-weight:700">SECONDARY OVERLAY</span>
            </div>
            <div style="color:#CBD5E1;font-size:12px;margin:12px 0">One month is the closest horizon to the core 10–40 trading-day objective; three months is broad regime context. This overlay does not override participant-OI/CIS, the capital regime, sector leadership, or entry/stop rules.</div>
            <div style="display:flex;flex-wrap:wrap;gap:9px">{metric_cards}</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:7px;margin-top:12px">{input_cells}</div>
            <div style="background:#111827;border:1px solid #334155;border-radius:8px;padding:11px;margin-top:12px;color:#CBD5E1;font-size:12px">
                Raw 3M model score is in <strong style="color:#C4B5FD">Q{bucket}/5</strong>; historical 3M bucket accuracy {_format_pct(confidence.get('accuracy%'))} (n={q_count}). Bucket samples are small and are not a guarantee.
                <div style="margin-top:4px">{direction_note}</div>
                <div style="color:#94A3B8;margin-top:4px">{calibration_note}</div>
            </div>
            <h3 style="color:#E2E8F0;margin:17px 0 6px">Matched historical scenarios</h3>
            {scenario_cards}
            <h3 style="color:#E2E8F0;margin:17px 0 6px">Scenario-based level context</h3>
            {forecast_rows or '<div style="color:#94A3B8">No level estimate is available for this run.</div>'}
            <div style="font-size:11px;color:#64748B;margin-top:12px">Research only, not investment advice. Scenario samples can overlap; direction hit-rates are at or below their reported base rates. No forecast is a substitute for capital preservation.</div>
        </div>
        """

    @staticmethod
    def _weekly_coverage_text(scan):
        total = scan.get("total_scanned")
        scanned = scan.get("scanned_indices")
        failed = scan.get("failed_indices", [])
        if scanned is None and total is not None:
            scanned = max(int(total) - len(failed), 0)
        if total is None:
            coverage = "index-feed coverage not recorded"
        elif not scanned:
            coverage = f"NO CONCLUSION — 0/{int(total)} feeds usable"
        elif failed:
            coverage = f"PARTIAL — {int(scanned)}/{int(total)} feeds usable; {len(failed)} failed"
        else:
            coverage = f"FULL — {int(scanned)}/{int(total)} feeds usable"
        failed_names = ", ".join(str(name).replace("|", "\\|") for name in failed)
        if failed_names:
            coverage += f"; failed indices: {failed_names}"
        return coverage

    @staticmethod
    def _weekly_coverage_html(scan):
        total = scan.get("total_scanned")
        scanned = scan.get("scanned_indices")
        failed = scan.get("failed_indices", [])
        if scanned is None and total is not None:
            scanned = max(int(total) - len(failed), 0)
        if total is None:
            coverage = "Index-feed coverage was not recorded by this scan."
        elif not scanned:
            coverage = f"⚠️ No conclusion: 0/{int(total)} index feeds returned usable weekly history."
        elif failed:
            coverage = f"⚠️ Partial scan: {int(scanned)}/{int(total)} feeds usable; {len(failed)} feed(s) failed."
        else:
            coverage = f"✅ Full scan: {int(scanned)}/{int(total)} index feeds usable."
        failed_names = ", ".join(escape(str(name)) for name in failed[:8])
        if len(failed) > 8:
            failed_names += f" and {len(failed) - 8} more"
        if failed_names:
            coverage += f" Failed feeds: {failed_names}."
        return coverage

    @staticmethod
    def _weekly_near_misses_html(scan):
        near = scan.get("near_misses", [])
        if not near:
            return ""
        rows = "".join(
            f"<tr><td style='padding:7px'>{escape(str(row.get('name', 'Index')))}</td>"
            f"<td style='padding:7px'>{row.get('score', 0)}/100</td>"
            f"<td style='padding:7px'>{row.get('wick_pct', 0):.1f}%</td>"
            f"<td style='padding:7px'>{row.get('close_in_range_pct', 0):.1f}%</td>"
            f"<td style='padding:7px'>{escape(', '.join(row.get('confluences', [])[:2]))}</td></tr>"
            for row in near[:6]
        )
        return f"""
        <div style="margin-top:14px;color:#CBD5E1;font-size:12px"><strong>Near-misses:</strong> {len(near)} index sweep(s) failed one or more quality gates; highest-scoring candidates:</div>
        <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;color:#CBD5E1;font-size:12px;margin-top:5px">
            <thead><tr style="background:#1E293B;color:#94A3B8"><th>INDEX</th><th>SCORE</th><th>WICK</th><th>CLOSE IN RANGE</th><th>OBSERVED CONFLUENCE</th></tr></thead><tbody>{rows}</tbody>
        </table></div>
        """

    def generate_html_report(self, calc_res, regime_res, sector_res, macro_res, daily_sweep_res=None, weekly_sweep_res=None, mtf_res=None, scenario_res=None):
        date_str = calc_res["date"]
        display_date = calc_res["display_date"]
        cis = calc_res["cis_score"]
        fii_ratio = calc_res["fii_long_ratio"]
        fii_stk_3d = calc_res["fii_stk_flow_3d"]
        flow_3d_complete = calc_res.get("fii_stk_flow_3d_complete", True)
        flow_3d_sample = calc_res.get("fii_stk_flow_3d_sample_days", 3)
        flow_3d_display = f"{fii_stk_3d:+,}" if flow_3d_complete else "N/A"
        flow_3d_color = ("#10B981" if fii_stk_3d > 0 else "#EF4444" if fii_stk_3d < 0 else "#94A3B8") if flow_3d_complete else "#94A3B8"
        flow_3d_description = (
            "Institutional Stock Accumulation" if fii_stk_3d > 0 else
            "Institutional Stock Distribution" if fii_stk_3d < 0 else
            "No net change" if flow_3d_complete else
            f"Insufficient history ({flow_3d_sample}/3 daily changes)"
        )
        oi_age = calc_res.get("oi_age_days")
        oi_source = escape(str(calc_res.get("oi_source", "not recorded")))
        oi_status = escape(str(calc_res.get("oi_data_status", "not recorded")))
        oi_quality_note = f"Participant OI: {oi_source} · {oi_status}" + (f" · {oi_age} day(s) old" if oi_age is not None else "")

        regime_name = regime_res["regime_name"]
        regime_desc = regime_res["regime_desc"]
        signal = regime_res["primary_signal"]
        signal_color = regime_res["signal_color"]
        cap_pct = regime_res["capital_allocation_pct"]
        cash_pct = regime_res["cash_reserve_pct"]
        action_text = regime_res["action_instructions"]
        
        daily_scan = self._normalize_daily_scan(daily_sweep_res)
        daily_sweep_res = daily_scan["setups"]
        daily_coverage_html = self._daily_coverage_html(daily_scan)
        weekly_scan = self._normalize_weekly_scan(weekly_sweep_res)
        is_friday_report = weekly_scan is not None
        weekly_hits = weekly_scan.get("weekly_hits", []) if weekly_scan else []
        weekly_edition_label = (
            "🗓️ Friday Edition" if weekly_scan and weekly_scan.get("is_friday", True)
            else "🗓️ Manual Weekly Scan" if weekly_scan
            else ""
        )
        mtf_res = mtf_res or {"has_signals": False, "actionable": [], "triggered": []}
        scenario_section_html = self._scenario_section_html(scenario_res)
        sector_coverage_text = self._sector_coverage_text(sector_res)
        sector_coverage_html = (
            f'<div style="color:#FBBF24;font-size:11px;margin:0 0 12px">{escape(sector_coverage_text)}</div>'
            if sector_coverage_text else ""
        )
        mtf_feed_note_html = ""
        if mtf_res.get("status") in {"partial", "unavailable"}:
            errors = mtf_res.get("errors", [])
            error_details = []
            for row in errors[:5]:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("name", "index"))
                if row.get("timeframe"):
                    label += f" ({row['timeframe']})"
                if row.get("reason"):
                    label += f": {row['reason']}"
                error_details.append(escape(label))
            extra = f" Feed issues: {'; '.join(error_details)}" if error_details else ""
            if len(errors) > 5:
                extra += f"; and {len(errors) - 5} more" if extra else f" Feed issues: {len(errors)} recorded"
            mtf_feed_note_html = (
                f'<div style="color:#FBBF24;font-size:11px;margin:-8px 0 16px">'
                f"MTF scan status: {escape(str(mtf_res.get('status')))}; daily index history coverage "
                f"{mtf_res.get('scanned_indices', 0)}/{mtf_res.get('total_indices', 0)}. "
                f"An empty signal list is not a no-signal conclusion.{extra}</div>"
            )

        # Signal-only MTF setup card is suppressed when no trap/MSS exists; feed health remains visible.
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
            if daily_scan.get("scanned_indices") == 0:
                daily_empty_message = "No conclusion: zero daily index feeds returned valid recent history; check the failed-feed list."
            elif daily_scan.get("failed_indices"):
                daily_empty_message = "No qualifying setup among the available feeds; the daily scan was partial."
            else:
                daily_empty_message = "No active daily liquidity sweep setups triggered in the scanned index feeds."
            daily_sweep_cards_html = f"""
            <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 20px; text-align: center; color: #94A3B8;">
                ⚡ {daily_empty_message}
            </div>
            """

        # Build Weekly Sweep Engine Section (Friday Edition)
        weekly_section_html = ""
        if is_friday_report:
            weekly_cards_html = ""
            weekly_coverage_html = self._weekly_coverage_html(weekly_scan)
            weekly_near_misses_html = self._weekly_near_misses_html(weekly_scan)
            if weekly_hits:
                for wk_hit in weekly_hits:
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
                                <span style="color: #64748B; font-size: 12px; margin-left: 6px;">({wk_hit.get('category', 'Index')} · {wk_hit.get('data_source', 'index history')})</span>
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
                scanned = weekly_scan.get("scanned_indices")
                if scanned is None:
                    scanned = weekly_scan.get("total_scanned", 0)
                if int(scanned or 0) == 0:
                    empty_message = "⚠️ No conclusion: the weekly engine could not evaluate any index because usable history was unavailable."
                elif weekly_scan.get("failed_indices"):
                    empty_message = "⚠️ No qualifying setup in the feeds that were available; this was a partial scan, not an all-clear."
                else:
                    empty_message = "No qualifying multi-week liquidity sweep was detected in the completed weekly candles."
                weekly_cards_html = f"""
                <div style="background: #030712; border: 1px solid #1E293B; border-radius: 12px; padding: 18px; text-align: center; color: #CBD5E1;">
                    ⚡ {empty_message}
                </div>
                """
                
            weekly_section_html = f"""
            <!-- WEEKLY INDEX LIQUIDITY SWEEP RADAR -->
            <div class="card" style="border: 1px solid #8B5CF6; box-shadow: 0 0 20px rgba(139, 92, 246, 0.15);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;">
                    <h2 style="margin: 0; font-size: 20px; color: #A78BFA; display: flex; align-items: center; gap: 8px;">
                        🗓️ NSE INDEX WEEKLY LIQUIDITY SWEEP RADAR
                    </h2>
                    <span style="background: rgba(139, 92, 246, 0.2); color: #C4B5FD; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase;">
                        Multi-Week Positional Horizon (2-6 Weeks)
                    </span>
                </div>
                <div style="color: #94A3B8; font-size: 13px; margin-bottom: 10px;">
                    Completed weekly candles only. Fractal, 26W / 52W liquidity-pool sweeps are reported for 2–6 week positional context; individual stocks are never scanned.
                </div>
                <div style="font-size:12px;margin-bottom:12px;color:#CBD5E1">Scan date: {escape(str(weekly_scan.get('scan_date') or 'not recorded'))} · {weekly_coverage_html}</div>
                {weekly_cards_html}
                {weekly_near_misses_html}
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
                try:
                    px = float(data.get("current"))
                    price_ok = px > 0 and px == px and abs(px) != float("inf")
                except (TypeError, ValueError):
                    px, price_ok = None, False
                try:
                    chg = float(data.get("change_pct"))
                    change_ok = chg == chg and abs(chg) != float("inf")
                except (TypeError, ValueError):
                    chg, change_ok = None, False
                chg_c = "#10B981" if change_ok and chg >= 0 else "#EF4444" if change_ok else "#64748B"
                status = str(data.get("status", "ok" if price_ok else "unavailable"))
                as_of = data.get("as_of")
                meta = f"{escape(str(data.get('symbol', '')))}" + (f" · {escape(str(as_of))}" if as_of else "")
                change_text = f"{chg:+.2f}%" if change_ok else "Change unavailable"
                macro_cards_html += f"""
                <div style="background: #0F172A; border: 1px solid #1E293B; border-radius: 10px; padding: 12px 16px; flex: 1; min-width: 140px;">
                    <div style="color: #94A3B8; font-size: 12px; font-weight: 600;">{label}</div>
                    <div style="color: #F8FAFC; font-size: 18px; font-weight: 800; margin: 4px 0;">{f'{px:,.2f}' if price_ok else 'Unavailable'} <span style="font-size: 12px; color: #64748B;">{unit if price_ok else ''}</span></div>
                    <div style="font-size: 12px; font-weight: 700; color: {chg_c};">{change_text} <span style="font-size: 11px; color: #64748B; font-weight: 400;">({note})</span></div>
                    <div style="font-size:10px;color:#64748B;margin-top:3px">{escape(status)} · {meta}</div>
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
                        Institutional Intelligence Report {'• ' + weekly_edition_label if weekly_edition_label else ''}
                    </span>
                    <h1 style="margin: 8px 0 4px 0; font-size: 28px; font-weight: 900; color: #FFFFFF;">
                        Smart Money Daily Market Prediction
                    </h1>
                    <div style="color: #94A3B8; font-size: 14px;">
                        Date: <strong style="color: #E2E8F0;">{display_date}</strong> | Official NSE Participant Open Interest & Quantitative Analytics
                    </div>
                    <div style="color:#64748B;font-size:11px;margin-top:3px">{oi_quality_note}</div>
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
                    <div style="font-size: 24px; font-weight: 900; color: {flow_3d_color}; margin: 6px 0;">
                        {flow_3d_display}
                    </div>
                    <div style="color: #94A3B8; font-size: 12px;">
                        {flow_3d_description}
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

        {scenario_section_html}

        {weekly_section_html}

        {mtf_section_html}
        {mtf_feed_note_html}

        <!-- DAILY NSE INDEX LIQUIDITY SWEEP & CONFLUENCE RADAR -->
        <div class="card">
            <h2 style="margin-top: 0; font-size: 20px; color: #F43F5E; display: flex; align-items: center; gap: 8px;">
                🎯 NSE INDEX DAILY LIQUIDITY SWEEP & REVERSAL RADAR
            </h2>
            <div style="color: #94A3B8; font-size: 13px; margin-bottom: 16px;">
                Daily multi-confluence screening across Broad Market, Sectoral & Thematic NSE Indices detecting Stop-Loss Sweeps, Hammer Rejection Wicks, Bullish RSI Divergences, and Fair Value Gaps (FVGs). <em>(Runs every day)</em>.
            </div>
            <div style="font-size:12px;margin-bottom:12px;color:#CBD5E1">Scan date: {escape(str(daily_scan.get('scan_date') or 'not recorded'))} · {daily_coverage_html}</div>
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
            {sector_coverage_html}
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
        md = self._generate_markdown(calc_res, regime_res, sector_res, macro_res, daily_scan, weekly_sweep_res, mtf_res, scenario_res)
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

    def _scenario_section_markdown(self, scenario_res):
        if not scenario_res or not scenario_res.get("available"):
            reason = (scenario_res or {}).get("error", "Live NIFTY/VIX history was not available.")
            return (
                "\n---\n\n## 🧭 NIFTY Scenario Lab — 1–3 Month Context\n"
                f"**Unavailable:** {reason}. No archived forecast was used as a live fallback. "
                "The core Smart Money report is unaffected.\n"
            )

        probs = scenario_res.get("probabilities", {})
        confidence = scenario_res.get("confidence_bucket", {})
        accuracy = scenario_res.get("accuracy", {})
        inputs = scenario_res.get("inputs", {})
        composite = scenario_res.get("composite", {})
        rows = [
            ("NIFTY positive return, 1M", "y_up_1M"),
            ("NIFTY positive return, 3M", "y_up_3M"),
            ("5%+ drawdown within 3M", "y_dip5_3M"),
            ("5%+ rally within 3M", "y_rally5_3M"),
        ]
        table = "| Outcome | Calibrated probability | Base rate | Walk-forward hit rate | AUC |\n| :--- | ---: | ---: | ---: | ---: |\n"
        for label, key in rows:
            record = probs.get(key, {})
            auc = record.get("oos_auc")
            table += (
                f"| {label} | {_format_probability(record.get('calibrated', 0))} "
                f"(raw {_format_probability(record.get('raw', 0))}) | "
                f"{_format_pct(record.get('base_rate_pct'))} | "
                f"{_format_pct(record.get('oos_hit_pct'))} | {auc if auc is not None else '—'} |\n"
            )

        matched_rows = ""
        for row in scenario_res.get("matched_scenarios", []):
            one, three = row.get("one_month", {}), row.get("three_month", {})
            name = str(row.get("name", row.get("key", "Scenario"))).replace("|", "\\|")
            rule = str(row.get("rule", "")).replace("|", "\\|")
            matched_rows += (
                f"| {name} | {row.get('events', '—')} | "
                f"{_format_pct(one.get('med'), signed=True)} / {_format_pct(one.get('up%'))} | "
                f"{_format_pct(three.get('med'), signed=True)} / {_format_pct(three.get('up%'))} | "
                f"{_format_pct(row.get('typical_dip_3m_pct'), signed=True)} / "
                f"{_format_pct(row.get('typical_rally_3m_pct'), signed=True)} | {rule} |\n"
            )
        if not matched_rows:
            matched_rows = "| No named historical scenario matched | — | — | — | — | — |\n"

        forecast_lines = ""
        if composite:
            forecast_lines = (
                f"\n- **1M blend context:** {_format_pct(composite.get('one_month_median_pct'), signed=True)} "
                f"→ approximately {float(composite.get('one_month_level', 0)):,.0f}.\n"
                f"- **3M blend context:** {_format_pct(composite.get('three_month_median_pct'), signed=True)} "
                f"→ approximately {float(composite.get('three_month_level', 0)):,.0f}.\n"
            )
            if composite.get("typical_dip_3m_pct") is not None:
                forecast_lines += (
                    f"- Matched-scenario typical 3M dip/rally: "
                    f"{_format_pct(composite.get('typical_dip_3m_pct'), signed=True)} "
                    f"(≈{float(composite['typical_dip_level']):,.0f}) / "
                    f"{_format_pct(composite.get('typical_rally_3m_pct'), signed=True)} "
                    f"(≈{float(composite['typical_rally_level']):,.0f}).\n"
                )
            forecast_lines += f"- Estimate method: {composite.get('estimate_method', 'model/scenario blend')}; context only, not a target.\n"

        forecast_text = forecast_lines or "No level estimate is available for this run."
        return f"""
---

## 🧭 NIFTY Scenario Lab — 1–3 Month Market Context
**Fresh inputs as of:** `{scenario_res.get('as_of', 'unknown')}` · **Model/statistics snapshot:** `{scenario_res.get('model_snapshot_as_of', 'unknown')}`

{table}

**Raw 3M confidence bucket:** Q{confidence.get('bucket', '—')}/5; historical bucket accuracy {_format_pct(confidence.get('accuracy%'))} (n={confidence.get('n', '—')}). This sample is small and is not a guarantee.

**Inputs:** NIFTY {float(inputs.get('nifty', 0)):,.2f}; India VIX {float(inputs.get('india_vix', 0)):.2f} ({float(inputs.get('india_vix_pct', 0)):.1f}th percentile); US VIX {float(inputs.get('us_vix', 0)):.2f} ({float(inputs.get('us_vix_pct', 0)):.1f}th percentile, one-session lag); RSI-14 {float(inputs.get('rsi14', 0)):.1f}; distance from 200 EMA {_format_pct(inputs.get('dist200'), signed=True)}; 52-week-high drawdown {_format_pct(inputs.get('dd252'), signed=True)}; distance above 6-month low {_format_pct(inputs.get('dist6mlow'), signed=True)}; bullish atoms {inputs.get('bull_count', 0)}/7.

### Matched historical scenarios
| Scenario | Episodes | 1M median / up-rate | 3M median / up-rate | Typical 3M dip / rally | Rule |
| :--- | ---: | ---: | ---: | ---: | :--- |
{matched_rows}
### Scenario level context
{forecast_text}

**Honest scorecard:** NIFTY 1M direction {_format_pct(accuracy.get('nifty_dir_1M'))} vs {_format_pct(accuracy.get('nifty_base_1M'))} base rate (AUC {accuracy.get('dir1M_auc', '—')}); 3M direction {_format_pct(accuracy.get('nifty_dir_3M'))} vs {_format_pct(accuracy.get('nifty_base_3M'))} base rate (AUC {accuracy.get('dir3M_auc', '—')}). {accuracy.get('calibration_note', '')}

*Overlay only: 1M is the closest horizon to the core 10–40 trading-day objective; 3M is longer-term context. Do not replace the primary participant-OI/CIS regime, sector confluence, or entry/stop rules. Research only, not investment advice.*
"""

    def _generate_markdown(self, calc_res, regime_res, sector_res, macro_res, daily_sweep_res=None, weekly_sweep_res=None, mtf_res=None, scenario_res=None):
        display_date = calc_res["display_date"]
        cis = calc_res["cis_score"]
        fii_ratio = calc_res["fii_long_ratio"]
        fii_stk_3d = calc_res["fii_stk_flow_3d"]
        flow_3d_complete = calc_res.get("fii_stk_flow_3d_complete", True)
        flow_3d_sample = calc_res.get("fii_stk_flow_3d_sample_days", 3)
        flow_3d_display = f"{fii_stk_3d:+,} contracts" if flow_3d_complete else f"N/A (only {flow_3d_sample}/3 daily changes)"
        oi_source = str(calc_res.get("oi_source", "not recorded"))
        oi_status = str(calc_res.get("oi_data_status", "not recorded"))
        oi_age = calc_res.get("oi_age_days")
        oi_quality_note = f"{oi_source} · {oi_status}" + (f" · {oi_age} day(s) old" if oi_age is not None else "")
        signal = regime_res["primary_signal"]
        daily_scan = self._normalize_daily_scan(daily_sweep_res)
        daily_sweep_res = daily_scan["setups"]
        daily_coverage_text = self._daily_coverage_text(daily_scan)
        sector_coverage_text = self._sector_coverage_text(sector_res)
        weekly_scan = self._normalize_weekly_scan(weekly_sweep_res)
        weekly_hits = weekly_scan.get("weekly_hits", []) if weekly_scan else []
        is_friday_report = weekly_scan is not None
        weekly_edition_label = (
            "🗓️ Friday Edition" if weekly_scan and weekly_scan.get("is_friday", True)
            else "🗓️ Manual Weekly Scan" if weekly_scan
            else ""
        )
        
        md = f"""# 🏛️ Smart Money Institutional Prediction Report — {display_date} {'(' + weekly_edition_label + ')' if weekly_edition_label else ''}

**Primary Signal**: `{signal}`
**Market Regime**: `{regime_res['regime_name']}`
**Composite Score (CIS)**: `{cis:+.1f} / 10`
**FII Index Long Ratio**: `{fii_ratio}%`
**FII 3-Day Stock Futures Flow**: `{flow_3d_display}`
**Participant OI data quality**: `{oi_quality_note}`
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
        md += self._scenario_section_markdown(scenario_res)
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
        if mtf_res.get("status") in {"partial", "unavailable"}:
            error_details = []
            for row in mtf_res.get("errors", [])[:5]:
                if not isinstance(row, dict):
                    continue
                label = str(row.get("name", "index"))
                if row.get("timeframe"):
                    label += f" ({row['timeframe']})"
                if row.get("reason"):
                    label += f": {row['reason']}"
                error_details.append(label.replace("|", "\\|"))
            extra = f" Feed issues: {'; '.join(error_details)}." if error_details else ""
            if len(mtf_res.get("errors", [])) > 5:
                extra += f" And {len(mtf_res['errors']) - 5} more."
            md += (
                f"\n**MTF scan status:** {mtf_res.get('status')}; daily index history coverage "
                f"{mtf_res.get('scanned_indices', 0)}/{mtf_res.get('total_indices', 0)}. "
                f"An empty signal list is not a no-signal conclusion.{extra}\n"
            )

        if is_friday_report:
            scan_date = weekly_scan.get("scan_date") or "not recorded"
            md += f"""
---

## 🗓️ NSE Index Weekly Liquidity Sweep Radar (2–6 Week Positional)
Completed weekly candles only; the scheduled scan runs in the Friday 9:00 PM IST report. Individual stocks are never scanned.

**Scan date:** `{scan_date}` · **Data coverage:** {self._weekly_coverage_text(weekly_scan)} · **Qualifying setups:** {len(weekly_hits)} · **Near-misses:** {len(weekly_scan.get('near_misses', []))}

| Index Name | Category | Grade & Score | Weekly Close | Weekly Low | Swept Support | Wick % | Invalidation SL | Confluences |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |
"""
            if weekly_hits:
                for wk in weekly_hits:
                    w_confs = ", ".join(wk.get("confluences", [])[:2]).replace("|", "\\|")
                    md += f"| {wk['name']} | {wk.get('category', 'Index')} | {wk.get('tier_badge', 'WEEKLY')} ({wk.get('score', 0)}/100) | {wk.get('current_price', 0):,.1f} | {wk.get('weekly_low', 0):,.1f} | {wk.get('swept_level', 0):,.1f} ({wk.get('pool_type', 'Low')}) | {wk.get('wick_pct', 0):.1f}% | {wk.get('stop_loss_level', 0):,.1f} | {w_confs} |\n"
            else:
                scanned = weekly_scan.get("scanned_indices")
                if scanned is None:
                    scanned = weekly_scan.get("total_scanned", 0)
                if int(scanned or 0) == 0:
                    no_setup = "*No conclusion — zero index feeds were usable; check the failure list.*"
                elif weekly_scan.get("failed_indices"):
                    no_setup = "*No qualifying setup among available feeds; scan was partial.*"
                else:
                    no_setup = "*No qualifying weekly index sweep detected.*"
                md += f"| {no_setup} | - | - | - | - | - | - | - | - |\n"

            near_misses = weekly_scan.get("near_misses", [])
            if near_misses:
                md += "\n### Weekly near-misses (quality gate not met)\n\n| Index | Score | Wick | Close in range | Observed confluences |\n| :--- | ---: | ---: | ---: | :--- |\n"
                for row in near_misses[:6]:
                    name = str(row.get("name", "Index")).replace("|", "\\|")
                    confluences = ", ".join(row.get("confluences", [])[:2]).replace("|", "\\|")
                    md += f"| {name} | {row.get('score', 0)}/100 | {row.get('wick_pct', 0):.1f}% | {row.get('close_in_range_pct', 0):.1f}% | {confluences} |\n"
        else:
            md += "\n---\n\n## 🗓️ Weekly Index Sweep Radar\nRuns after the completed Friday weekly candle close and appears in the Friday report/email. `python src/main.py --weekly` can be used for a manual scan.\n"

        md += f"""
---

## 🎯 NSE Index Daily Liquidity Sweep Radar (Daily Routine)
Daily multi-confluence screening across Broad Market, Sectoral & Thematic NSE Indices detecting Stop-Loss Sweeps, Hammer Rejection Wicks, RSI Divergences, and FVGs.

**Scan date:** `{daily_scan.get('scan_date', 'not recorded')}` · **Feed coverage:** {daily_coverage_text}

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
            if daily_scan.get("scanned_indices") == 0:
                daily_empty_message = "No conclusion — zero feeds usable; inspect failures"
            elif daily_scan.get("failed_indices"):
                daily_empty_message = "No qualifying setup among available feeds; scan partial"
            else:
                daily_empty_message = "No active daily index sweep triggers in available feeds"
            md += f"| *{daily_empty_message}* | - | - | - | - | - | - | - | - |\n"

        md += f"""
---

## 🔄 Sector Rotation Ranking
{sector_res.get('rotation_summary', '')}

{sector_coverage_text}

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
