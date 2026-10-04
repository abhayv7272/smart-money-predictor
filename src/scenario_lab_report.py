"""Load and render the NIFTY Scenario Lab bundle inside prediction reports."""

import html as html_lib
import json
import math
import zipfile

APP_DATA_MEMBER = "GITHUB_READY/data/app_data.json"
FORECAST_MEMBER = "GITHUB_READY/data/live_forecast.json"
INDEX_MEMBER = "GITHUB_READY/index.html"


def load_scenario_lab_data(archive_path):
    """Read report-ready data and the self-contained app directly from the tracked ZIP."""
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = set(archive.namelist())
            if APP_DATA_MEMBER not in members:
                return None
            app_data = json.loads(archive.read(APP_DATA_MEMBER).decode("utf-8"))
            forecast = (
                json.loads(archive.read(FORECAST_MEMBER).decode("utf-8"))
                if FORECAST_MEMBER in members
                else {}
            )
            index_html = (
                archive.read(INDEX_MEMBER).decode("utf-8")
                if INDEX_MEMBER in members
                else ""
            )
    except (OSError, KeyError, UnicodeDecodeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[WARN] NIFTY Scenario Lab data could not be loaded: {exc}")
        return None

    if not isinstance(app_data, dict):
        return None
    if not isinstance(forecast, dict):
        forecast = {}
    return {"app_data": app_data, "forecast": forecast, "index_html": index_html}


def _first_dict(*values):
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _view(data):
    if not isinstance(data, dict):
        return None

    app_data = data.get("app_data") or {}
    forecast = data.get("forecast") or {}
    archived_live = app_data.get("live") or {}
    forecast_inputs = forecast.get("inputs")
    inputs = _first_dict(forecast_inputs, archived_live.get("inputs"))
    probs_cal = _first_dict(forecast.get("probs_cal"), archived_live.get("probs_cal"))
    probs_raw = _first_dict(forecast.get("probs_raw"), archived_live.get("probs_raw"))
    scenarios_matched = forecast.get("scenarios_matched")
    if not isinstance(scenarios_matched, list):
        scenarios_matched = archived_live.get("scenarios_matched", [])
    if not isinstance(scenarios_matched, list):
        scenarios_matched = []

    meta = app_data.get("meta") or {}
    as_of = (
        forecast.get("as_of")
        or archived_live.get("date")
        or meta.get("as_of")
        or "Unknown"
    )
    quintile = forecast.get("quintile")
    if not isinstance(quintile, dict):
        quintile = None
        raw_probability = probs_raw.get("y_up_3M")
        try:
            raw_probability = float(raw_probability)
        except (TypeError, ValueError):
            raw_probability = None
        if raw_probability is not None:
            for candidate in app_data.get("quintiles", []):
                try:
                    low = float(candidate.get("p_lo", 0))
                    high = float(candidate.get("p_hi", 1))
                    if low <= raw_probability <= high:
                        quintile = candidate
                        break
                except (AttributeError, TypeError, ValueError):
                    continue

    return {
        "app_data": app_data,
        "inputs": inputs,
        "probs_cal": probs_cal,
        "probs_raw": probs_raw,
        "scenarios_matched": scenarios_matched,
        "as_of": as_of,
        "quintile": quintile,
    }


def _number(value, decimals=1, signed=False):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(value):
        return "—"
    spec = f"{'+' if signed else ''},.{decimals}f"
    return format(value, spec)


def _probability(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(value):
        return "—"
    # The archive stores probabilities as fractions; tolerate already-percent values too.
    percent = value * 100 if abs(value) <= 1 else value
    return f"{percent:.1f}%"


def _percent_points(value, signed=False, decimals=1):
    formatted = _number(value, decimals=decimals, signed=signed)
    return "—" if formatted == "—" else f"{formatted}%"


def _escape(value):
    return html_lib.escape("—" if value is None else str(value), quote=True)


def _md(value):
    return str("—" if value is None else value).replace("|", "\\|").replace("\n", " ").strip()


def _scenario_keys(app_data):
    scenarios = app_data.get("scenarios") or {}
    order = app_data.get("scenario_order")
    if not isinstance(order, list):
        order = []
    return [key for key in order if key in scenarios] + [
        key for key in scenarios if key not in order
    ]


def _scenario_stats(scenario):
    return scenario.get("stats_all") or scenario.get("stats_2023+") or {}


def _matched_scenario_html(view):
    app_data = view["app_data"]
    scenarios = app_data.get("scenarios") or {}
    cards = []
    for key in view["scenarios_matched"]:
        scenario = scenarios.get(key)
        if not isinstance(scenario, dict):
            continue
        stats = _scenario_stats(scenario)
        ret3 = stats.get("ret3") or {}
        history = (
            f"3M median {_percent_points(ret3.get('med'), signed=True)} · "
            f"historical up-rate {_percent_points(ret3.get('up%'))} · "
            f"n={_number(ret3.get('n', stats.get('events')), decimals=0)} resolved 3M outcomes"
        )
        cards.append(
            f'''<div style="background:#0F172A;border:1px solid #334155;border-left:4px solid #38BDF8;border-radius:10px;padding:14px;margin:10px 0">
                <div style="font-weight:800;color:#F8FAFC">{_escape(scenario.get("name", key))}</div>
                <div style="color:#94A3B8;font-size:12px;margin:4px 0 8px">Rule: {_escape(scenario.get("rule", "—"))}</div>
                <div style="color:#CBD5E1;font-size:13px">{history}</div>
                <div style="color:#E2E8F0;font-size:13px;margin-top:8px"><b>Historical playbook:</b> {_escape(scenario.get("action", "—"))}</div>
            </div>'''
        )
    if cards:
        return "".join(cards)
    return '<p style="color:#CBD5E1">No predefined historical scenario matched this archive snapshot.</p>'


def _scenario_library_html(view):
    app_data = view["app_data"]
    scenarios = app_data.get("scenarios") or {}
    matched = set(view["scenarios_matched"])
    rows = []
    for key in _scenario_keys(app_data):
        scenario = scenarios.get(key) or {}
        stats = _scenario_stats(scenario)
        ret1 = stats.get("ret1") or {}
        ret3 = stats.get("ret3") or {}
        marker = "✅ MATCHED" if key in matched else "—"
        background = "background:#10251D" if key in matched else ""
        rows.append(
            f'''<tr style="{background};border-bottom:1px solid #1E293B">
                <td style="padding:9px;min-width:190px"><b>{_escape(scenario.get("name", key))}</b><div style="color:#94A3B8;font-size:11px;margin-top:3px">{_escape(scenario.get("rule", "—"))}</div></td>
                <td style="padding:9px;white-space:nowrap;color:{'#34D399' if key in matched else '#94A3B8'}">{marker}</td>
                <td style="padding:9px;white-space:nowrap">{_percent_points(ret1.get("med"), signed=True)} / {_percent_points(ret1.get("up%"))}</td>
                <td style="padding:9px;white-space:nowrap">{_percent_points(ret3.get("med"), signed=True)} / {_percent_points(ret3.get("up%"))}</td>
                <td style="padding:9px;white-space:nowrap">{_percent_points(stats.get("dip3"), signed=True)} / {_percent_points(stats.get("rally3"), signed=True)}</td>
                <td style="padding:9px;text-align:right">{_number(ret3.get("n", stats.get("events")), decimals=0)}</td>
            </tr>'''
        )
    return "".join(rows) or '<tr><td colspan="6" style="padding:10px">Scenario statistics are unavailable in the archive.</td></tr>'


def _baseline_accuracy(accuracy, record, hit_key, base_key):
    if base_key:
        baseline = accuracy.get(base_key)
        if baseline is not None:
            return baseline
    if hit_key.startswith("vix_"):
        return accuracy.get("vix_baseline")
    try:
        event_rate = float(record.get("base_rate%"))
    except (TypeError, ValueError):
        return None
    # Hit-rate baselines use the most common class (e.g. no 5%+ dip), not
    # the event probability itself.
    return max(event_rate, 100.0 - event_rate)


def _accuracy_rows_html(view):
    app_data = view["app_data"]
    accuracy = app_data.get("accuracy") or {}
    calibration = app_data.get("calibration") or {}
    definitions = [
        ("NIFTY direction · 1M", "nifty_dir_1M", "nifty_base_1M", "dir1M_auc", "y_up_1M"),
        ("NIFTY direction · 3M", "nifty_dir_3M", "nifty_base_3M", "dir3M_auc", "y_up_3M"),
        ("3M dip greater than 5%", "dip_hit_3M", None, "dip_auc", "y_dip5_3M"),
        ("3M rally greater than 5%", "rally_hit_3M", None, "rally_auc", "y_rally5_3M"),
        ("India VIX direction · 1M", "vix_direction_1M", None, None, None),
        ("India VIX direction · 2M", "vix_direction_2M", None, None, None),
    ]
    rows = []
    for label, hit_key, base_key, auc_key, calibration_key in definitions:
        record = calibration.get(calibration_key) or {}
        hit = accuracy.get(hit_key)
        if hit is None:
            hit = record.get("oos_hit%")
        baseline = _baseline_accuracy(accuracy, record, hit_key, base_key)
        auc = accuracy.get(auc_key) if auc_key else None
        if hit is None:
            continue
        rows.append(
            f'''<tr style="border-bottom:1px solid #1E293B">
                <td style="padding:8px">{_escape(label)}</td>
                <td style="padding:8px;text-align:right">{_percent_points(hit)}</td>
                <td style="padding:8px;text-align:right">{_percent_points(baseline)}</td>
                <td style="padding:8px;text-align:right">{_number(auc, decimals=3) if auc is not None else "—"}</td>
            </tr>'''
        )
    return "".join(rows) or '<tr><td colspan="4" style="padding:10px">Walk-forward scorecard is unavailable in the archive.</td></tr>'


def _confidence_rows_html(view):
    rows = []
    quintiles = view["app_data"].get("quintiles") or []
    for bucket in sorted(quintiles, key=lambda item: item.get("bucket", 0)):
        rows.append(
            f'''<tr style="border-bottom:1px solid #1E293B">
                <td style="padding:7px">Q{_number(bucket.get("bucket"), decimals=0)}</td>
                <td style="padding:7px;text-align:right">{_probability(bucket.get("avg_conf"))}</td>
                <td style="padding:7px;text-align:right">{_percent_points(bucket.get("accuracy%"))}</td>
                <td style="padding:7px;text-align:right">{_number(bucket.get("n"), decimals=0)}</td>
            </tr>'''
        )
    return "".join(rows) or '<tr><td colspan="4" style="padding:10px">Confidence buckets are unavailable in the archive.</td></tr>'


def render_scenario_lab_html(data, report_date=None):
    """Render a compact, snapshot-labelled summary plus the archived interactive app."""
    view = _view(data)
    if not view:
        return ""

    app_data = view["app_data"]
    inputs = view["inputs"]
    probabilities = view["probs_cal"]
    accuracy = app_data.get("accuracy") or {}
    calibration = app_data.get("calibration") or {}
    quintile = view.get("quintile") or {}

    input_items = [
        ("NIFTY spot", _number(inputs.get("nifty"), decimals=2)),
        ("India VIX", f"{_number(inputs.get('india_vix'), decimals=2)} ({_number(inputs.get('india_vix_pct'), decimals=1)}th percentile)"),
        ("US VIX", f"{_number(inputs.get('us_vix'), decimals=2)} ({_number(inputs.get('us_vix_pct'), decimals=1)}th percentile)"),
        ("RSI-14", _number(inputs.get("rsi14"), decimals=1)),
        ("Distance from 200 EMA", _percent_points(inputs.get("dist200"), signed=True, decimals=2)),
        ("Drawdown from 52-week high", _percent_points(inputs.get("dd252"), signed=True, decimals=2)),
        ("Distance from 6-month low", _percent_points(inputs.get("dist6mlow"), signed=True, decimals=2)),
        ("Strength atoms", f"{_number(inputs.get('bull_count'), decimals=0)} / 7"),
    ]
    input_html = "".join(
        f'''<div style="background:#030712;border:1px solid #1E293B;border-radius:8px;padding:9px 11px">
            <div style="font-size:10px;color:#94A3B8;text-transform:uppercase">{_escape(label)}</div>
            <div style="font-size:14px;color:#F8FAFC;font-weight:700">{_escape(value)}</div>
        </div>'''
        for label, value in input_items
    )

    outputs = [
        ("NIFTY up · 1M", "y_up_1M", accuracy.get("nifty_base_1M")),
        ("NIFTY up · 3M", "y_up_3M", accuracy.get("nifty_base_3M")),
        ("3M dip > 5%", "y_dip5_3M", (calibration.get("y_dip5_3M") or {}).get("base_rate%")),
        ("3M rally > 5%", "y_rally5_3M", (calibration.get("y_rally5_3M") or {}).get("base_rate%")),
    ]
    output_html = "".join(
        f'''<div style="background:#030712;border:1px solid #1E293B;border-radius:10px;padding:13px">
            <div style="font-size:11px;color:#94A3B8;text-transform:uppercase">{_escape(label)}</div>
            <div style="font-size:25px;font-weight:900;color:#38BDF8;margin:3px 0">{_probability(probabilities.get(key))}</div>
            <div style="font-size:11px;color:#94A3B8">Historical base rate: {_percent_points(baseline)}</div>
        </div>'''
        for label, key, baseline in outputs
    )

    q_bucket = quintile.get("bucket")
    q_accuracy = quintile.get("accuracy%")
    q_sample = quintile.get("n")
    if q_bucket is not None:
        confidence_summary = (
            f"Q{_number(q_bucket, decimals=0)}/5 · historical 3M accuracy "
            f"{_percent_points(q_accuracy)} (n={_number(q_sample, decimals=0)})"
        )
    else:
        confidence_summary = "Confidence bucket unavailable"

    snapshot_note = (
        f"Snapshot date: {_escape(view['as_of'])}. Figures below are read from the supplied ZIP; "
        "the existing Smart Money daily pipeline does not refit or refresh this separate model."
    )
    if report_date and view["as_of"] != report_date:
        snapshot_note += f" Report date: {_escape(report_date)}."

    index_html = data.get("index_html", "")
    interactive_block = ""
    if index_html:
        srcdoc = html_lib.escape(index_html, quote=True)
        interactive_block = f'''<details style="margin-top:16px;background:#030712;border:1px solid #334155;border-radius:10px;padding:12px">
            <summary style="cursor:pointer;color:#38BDF8;font-weight:800">Open the full interactive Scenario Lab from the ZIP</summary>
            <p style="font-size:12px;color:#94A3B8">This embedded, self-contained app uses the snapshot shipped in the supplied archive. Some email clients block interactive embedded content; the summary above remains available.</p>
            <iframe title="Interactive NIFTY Market Scenario Predictor" loading="lazy" sandbox="allow-scripts" srcdoc="{srcdoc}" style="display:block;width:100%;height:950px;border:1px solid #334155;border-radius:8px;background:#fff"></iframe>
        </details>'''

    return f'''<!-- NIFTY SCENARIO LAB INTEGRATION -->
        <div class="card" style="border:1px solid #2563EB;box-shadow:0 0 20px rgba(37,99,235,.12)">
            <h2 style="margin-top:0;color:#60A5FA">🧭 NIFTY MARKET SCENARIO LAB · 1–3 MONTH OUTLOOK</h2>
            <div style="color:#94A3B8;font-size:12px;margin-bottom:14px">{snapshot_note}</div>
            <div style="background:#111827;border-left:4px solid #F59E0B;border-radius:6px;padding:10px 12px;color:#CBD5E1;font-size:12px;margin-bottom:14px">
                Archive confidence: <b style="color:#F8FAFC">{_escape(confidence_summary)}</b>. Historical sample sizes are limited; these probabilities and scenario returns are research estimates, not guarantees or investment advice.
            </div>
            <h3 style="color:#93C5FD;margin:12px 0 8px">Calibrated probability snapshot</h3>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px">{output_html}</div>
            <h3 style="color:#93C5FD;margin:18px 0 8px">Market inputs used by the Scenario Lab</h3>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px">{input_html}</div>
            <h3 style="color:#93C5FD;margin:18px 0 8px">Historical scenarios matched by this snapshot</h3>
            {_matched_scenario_html(view)}
            <details style="margin-top:14px;background:#030712;border:1px solid #334155;border-radius:10px;padding:12px">
                <summary style="cursor:pointer;color:#E2E8F0;font-weight:800">View the full eight-scenario historical library</summary>
                <div style="overflow-x:auto;margin-top:10px"><table style="width:100%;border-collapse:collapse;font-size:11px;color:#CBD5E1">
                    <thead><tr style="background:#1E293B;color:#94A3B8;text-align:left"><th style="padding:9px">Scenario / rule</th><th style="padding:9px">Status</th><th style="padding:9px">1M median / up-rate</th><th style="padding:9px">3M median / up-rate</th><th style="padding:9px">Typical dip / rally</th><th style="padding:9px;text-align:right">3M outcome n</th></tr></thead>
                    <tbody>{_scenario_library_html(view)}</tbody>
                </table></div>
            </details>
            <details style="margin-top:10px;background:#030712;border:1px solid #334155;border-radius:10px;padding:12px">
                <summary style="cursor:pointer;color:#E2E8F0;font-weight:800">View walk-forward accuracy and confidence buckets</summary>
                <div style="overflow-x:auto;margin-top:10px"><table style="width:100%;border-collapse:collapse;font-size:12px;color:#CBD5E1">
                    <thead><tr style="background:#1E293B;color:#94A3B8;text-align:left"><th style="padding:8px">Target</th><th style="padding:8px;text-align:right">Walk-forward hit rate</th><th style="padding:8px;text-align:right">Baseline accuracy</th><th style="padding:8px;text-align:right">AUC</th></tr></thead>
                    <tbody>{_accuracy_rows_html(view)}</tbody>
                </table></div>
                <div style="overflow-x:auto;margin-top:12px"><table style="width:100%;max-width:620px;border-collapse:collapse;font-size:12px;color:#CBD5E1">
                    <thead><tr style="background:#1E293B;color:#94A3B8;text-align:left"><th style="padding:7px">Bucket</th><th style="padding:7px;text-align:right">Average confidence</th><th style="padding:7px;text-align:right">3M accuracy</th><th style="padding:7px;text-align:right">n</th></tr></thead>
                    <tbody>{_confidence_rows_html(view)}</tbody>
                </table></div>
                <div style="color:#94A3B8;font-size:11px;margin-top:8px">The bundled walk-forward results cover the evaluation window reported by the archive and have small per-bucket sample sizes. In particular, Q5 accuracy is based on a limited historical sample.</div>
            </details>
            {interactive_block}
            <div style="color:#64748B;font-size:11px;margin-top:14px">Source: <a href="../nifty-scenario-lab-github.zip" style="color:#60A5FA">nifty-scenario-lab-github.zip</a> · Educational research only; not investment advice.</div>
        </div>
        <!-- END NIFTY SCENARIO LAB INTEGRATION -->'''


def _scenario_library_markdown(view):
    app_data = view["app_data"]
    scenarios = app_data.get("scenarios") or {}
    matched = set(view["scenarios_matched"])
    rows = []
    for key in _scenario_keys(app_data):
        scenario = scenarios.get(key) or {}
        stats = _scenario_stats(scenario)
        ret1 = stats.get("ret1") or {}
        ret3 = stats.get("ret3") or {}
        dip_rally = (
            f"{_percent_points(stats.get('dip3'), signed=True)} / "
            f"{_percent_points(stats.get('rally3'), signed=True)}"
        )
        rows.append(
            f"| {_md(scenario.get('name', key))} | {'Matched' if key in matched else '—'} | "
            f"{_percent_points(ret1.get('med'), signed=True)} / {_percent_points(ret1.get('up%'))} | "
            f"{_percent_points(ret3.get('med'), signed=True)} / {_percent_points(ret3.get('up%'))} | "
            f"{dip_rally} | {_number(ret3.get('n', stats.get('events')), decimals=0)} |"
        )
    return "\n".join(rows)


def _accuracy_markdown(view):
    app_data = view["app_data"]
    accuracy = app_data.get("accuracy") or {}
    calibration = app_data.get("calibration") or {}
    definitions = [
        ("NIFTY direction · 1M", "nifty_dir_1M", "nifty_base_1M", "dir1M_auc", "y_up_1M"),
        ("NIFTY direction · 3M", "nifty_dir_3M", "nifty_base_3M", "dir3M_auc", "y_up_3M"),
        ("3M dip greater than 5%", "dip_hit_3M", None, "dip_auc", "y_dip5_3M"),
        ("3M rally greater than 5%", "rally_hit_3M", None, "rally_auc", "y_rally5_3M"),
        ("India VIX direction · 1M", "vix_direction_1M", None, None, None),
        ("India VIX direction · 2M", "vix_direction_2M", None, None, None),
    ]
    rows = []
    for label, hit_key, base_key, auc_key, calibration_key in definitions:
        record = calibration.get(calibration_key) or {}
        hit = accuracy.get(hit_key)
        if hit is None:
            hit = record.get("oos_hit%")
        baseline = _baseline_accuracy(accuracy, record, hit_key, base_key)
        auc = accuracy.get(auc_key) if auc_key else None
        if hit is None:
            continue
        rows.append(
            f"| {_md(label)} | {_percent_points(hit)} | {_percent_points(baseline)} | "
            f"{_number(auc, decimals=3) if auc is not None else '—'} |"
        )
    return "\n".join(rows)


def render_scenario_lab_markdown(data, report_date=None):
    """Render the ZIP's current forecast and supporting research in Markdown."""
    view = _view(data)
    if not view:
        return ""

    app_data = view["app_data"]
    inputs = view["inputs"]
    probabilities = view["probs_cal"]
    accuracy = app_data.get("accuracy") or {}
    calibration = app_data.get("calibration") or {}
    quintile = view.get("quintile") or {}
    scenarios = app_data.get("scenarios") or {}
    matched_rows = []
    for key in view["scenarios_matched"]:
        scenario = scenarios.get(key)
        if not isinstance(scenario, dict):
            continue
        stats = _scenario_stats(scenario)
        ret3 = stats.get("ret3") or {}
        history = (
            f"3M median {_percent_points(ret3.get('med'), signed=True)}, "
            f"up-rate {_percent_points(ret3.get('up%'))}, "
            f"n={_number(ret3.get('n', stats.get('events')), decimals=0)} completed 3M outcomes"
        )
        matched_rows.append(
            f"| {_md(scenario.get('name', key))} | {history} | "
            f"{_md(scenario.get('action', '—'))} |"
        )
    if not matched_rows:
        matched_rows.append("| No predefined scenario matched | — | Use the probabilities as research context only. |")

    q_summary = "Confidence bucket unavailable"
    if quintile.get("bucket") is not None:
        q_summary = (
            f"Q{_number(quintile.get('bucket'), decimals=0)}/5, "
            f"historical 3M accuracy {_percent_points(quintile.get('accuracy%'))} "
            f"(n={_number(quintile.get('n'), decimals=0)})"
        )

    baseline_dip = (calibration.get("y_dip5_3M") or {}).get("base_rate%")
    baseline_rally = (calibration.get("y_rally5_3M") or {}).get("base_rate%")
    probability_rows = [
        ("NIFTY up · 1M", "y_up_1M", accuracy.get("nifty_base_1M")),
        ("NIFTY up · 3M", "y_up_3M", accuracy.get("nifty_base_3M")),
        ("3M dip greater than 5%", "y_dip5_3M", baseline_dip),
        ("3M rally greater than 5%", "y_rally5_3M", baseline_rally),
    ]
    probability_table = "\n".join(
        f"| {_md(label)} | {_probability(probabilities.get(key))} | {_percent_points(baseline)} |"
        for label, key, baseline in probability_rows
    )

    input_summary = (
        f"NIFTY **{_number(inputs.get('nifty'), decimals=2)}** · "
        f"India VIX **{_number(inputs.get('india_vix'), decimals=2)} "
        f"({_number(inputs.get('india_vix_pct'), decimals=1)}th percentile)** · "
        f"US VIX **{_number(inputs.get('us_vix'), decimals=2)} "
        f"({_number(inputs.get('us_vix_pct'), decimals=1)}th percentile)** · "
        f"RSI-14 **{_number(inputs.get('rsi14'), decimals=1)}** · "
        f"distance from 200 EMA **{_percent_points(inputs.get('dist200'), signed=True, decimals=2)}** · "
        f"52-week drawdown **{_percent_points(inputs.get('dd252'), signed=True, decimals=2)}** · "
        f"distance from 6-month low **{_percent_points(inputs.get('dist6mlow'), signed=True, decimals=2)}** · "
        f"strength atoms **{_number(inputs.get('bull_count'), decimals=0)}/7**"
    )
    return f'''---

## 🧭 NIFTY Market Scenario Lab — 1–3 Month Outlook

*Archive snapshot as of **{_md(view['as_of'])}**. The report pipeline reads the supplied ZIP but does not refit or refresh this separate model.{' Report date: **' + _md(report_date) + '**.' if report_date and view['as_of'] != report_date else ''}*

**Scenario Lab inputs:** {input_summary}

**Confidence bucket:** {q_summary}. This bucket is based on a limited historical sample.

### Calibrated probability snapshot

| Model output | Calibrated probability | Historical base rate |
| :--- | ---: | ---: |
{probability_table}

### Matched historical scenarios

| Scenario | Historical 3M result | Historical playbook (for research context) |
| :--- | :--- | :--- |
{chr(10).join(matched_rows)}

### Full historical scenario library

| Scenario | Current snapshot | 1M median / up-rate | 3M median / up-rate | Typical 3M dip / rally | 3M outcome n |
| :--- | :--- | ---: | ---: | ---: | ---: |
{_scenario_library_markdown(view)}

### Walk-forward accuracy context

| Target | Hit rate | Baseline accuracy | AUC |
| :--- | ---: | ---: | ---: |
{_accuracy_markdown(view)}

| Confidence bucket | Average confidence | 3M accuracy | n |
| :--- | ---: | ---: | ---: |
{chr(10).join(f"| Q{_number(q.get('bucket'), decimals=0)} | {_probability(q.get('avg_conf'))} | {_percent_points(q.get('accuracy%'))} | {_number(q.get('n'), decimals=0)} |" for q in sorted(app_data.get('quintiles', []) or [], key=lambda item: item.get('bucket', 0)))}

The archive's walk-forward hit rates are shown beside their reported baselines; scenario and confidence-bucket samples are small. Historical performance is not a guarantee of future returns. Educational research only, not investment advice.

Full interactive app: [nifty-scenario-lab-github.zip](../nifty-scenario-lab-github.zip).
'''
