"""Bounded pre-deployment diagnostics for OI and every market-data path.

Critical failures stop signal trust (notably stale/incomplete/discontinuous OI). Optional
Yahoo feeds are tested independently and reported as warnings so one failed endpoint cannot
hide results from the remaining fetch paths.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fetcher import FreeDataFetcher
from index_sweep_engine import IndexSweepEngine
from weekly_index_sweep_engine import WeeklyIndexSweepEngine
from mtf_index_sweep_engine import MTFIndexSweepEngine
from nifty_scenario_engine import NiftyScenarioEngine


def _run_check(name, callback, failures, warnings, critical=False):
    try:
        value = callback()
        return value
    except Exception as exc:
        message = f"{name}: {type(exc).__name__}: {exc}"
        print("FAIL" if critical else "WARN", message)
        (failures if critical else warnings).append(message)
        return None


def main():
    failures, warnings = [], []
    started = time.monotonic()
    fetcher = FreeDataFetcher()

    print("=== Official participant OI ===")
    oi = _run_check("Latest OI fetch/validation", fetcher.fetch_latest_participant_oi, failures, warnings, critical=True)
    history = None
    if oi:
        types = {row.get("client_type") for row in oi.get("raw_data", [])}
        print(
            f"OI {oi.get('date')} source={oi.get('source')} status={oi.get('data_status')} "
            f"age_days={oi.get('age_days')} participants={sorted(types)}"
        )
        if not {"Client", "DII", "FII", "Pro"}.issubset(types):
            failures.append("Latest OI response does not contain all four participant rows")
    history = _run_check(
        "Recent OI history", lambda: fetcher.fetch_recent_history(days_count=10),
        failures, warnings, critical=True,
    )
    if history is not None:
        count = history["date"].nunique()
        print(f"OI_HISTORY dates={count} range={history['date'].min()}..{history['date'].max()} rows={len(history)}")
        if count < 3:
            failures.append(f"Only {count} continuous OI dates are available")

    print("\n=== Macro benchmarks ===")
    macro = _run_check("Macro fetch", fetcher.fetch_global_macro, failures, warnings)
    if macro is not None:
        available = [key for key, value in macro.items() if value.get("status") in {"ok", "fallback"} and value.get("current") is not None]
        print(f"MACRO {len(available)}/{len(macro)} available: {', '.join(available) or 'none'}")
        for key, value in macro.items():
            if value.get("status") == "unavailable":
                warnings.append(f"Macro feed {key} unavailable: {value.get('error')}")
        if macro.get("nifty_50", {}).get("current") is None:
            warnings.append("Fresh NIFTY spot unavailable; report must suppress numerical spot levels")
        yield_value = macro.get("us_10y_yield", {}).get("current")
        if yield_value is not None and not (0 < float(yield_value) < 20):
            failures.append(f"US 10Y yield is outside sensible percent units: {yield_value}")

    print("\n=== NIFTY Scenario Lab ===")
    scenario = _run_check("Scenario Lab", lambda: NiftyScenarioEngine().run(), failures, warnings)
    if scenario:
        if scenario.get("available"):
            print(f"SCENARIO available as_of={scenario.get('as_of')} nifty={scenario.get('inputs', {}).get('nifty')}")
        else:
            warnings.append(f"Scenario overlay unavailable: {scenario.get('error')}")
            print(f"SCENARIO unavailable: {scenario.get('error')}")

    print("\n=== Sector-relative-strength feeds ===")
    sectors = _run_check("Sector history fetch", fetcher.fetch_sector_strength, failures, warnings)
    if sectors is not None:
        sources = sorted({row.get("data_source", "unknown") for row in sectors})
        sector_diag = fetcher.last_sector_diagnostics
        print(
            f"SECTORS status={sector_diag.get('status')} coverage="
            f"{sector_diag.get('scanned_indices')}/{sector_diag.get('total_indices')} "
            f"valid histories sources={sources} failed={sector_diag.get('failed_indices', [])}"
        )
        if sector_diag.get("status") in {"partial", "unavailable"}:
            warnings.append(
                f"Sector feed coverage {sector_diag.get('scanned_indices')}/{sector_diag.get('total_indices')}; "
                f"failed indices: {sector_diag.get('failed_indices', [])}"
            )

    print("\n=== Daily index sweep feeds ===")
    daily = _run_check("Daily sweep", lambda: IndexSweepEngine().scan_all_indices_detailed(), failures, warnings)
    if daily is not None:
        print(
            f"DAILY status={daily.get('status')} coverage={daily.get('scanned_indices')}/"
            f"{daily.get('total_indices')} setups={len(daily.get('setups', []))} "
            f"failed={daily.get('failed_indices', [])}"
        )
        if daily.get("scanned_indices", 0) == 0:
            warnings.append("No daily index history feeds were usable")

    print("\n=== Weekly index sweep feeds ===")
    weekly = _run_check("Weekly sweep", lambda: WeeklyIndexSweepEngine().scan_weekly_indices(), failures, warnings)
    if weekly is not None:
        print(
            f"WEEKLY status={weekly.get('status')} coverage={weekly.get('scanned_indices')}/"
            f"{weekly.get('total_scanned')} hits={len(weekly.get('weekly_hits', []))} "
            f"near={len(weekly.get('near_misses', []))} failed={weekly.get('failed_indices', [])}"
        )
        if weekly.get("scanned_indices", 0) == 0:
            warnings.append("No weekly index history feeds were usable")

    print("\n=== MTF daily/intraday feeds ===")
    mtf = _run_check("MTF sweep", lambda: MTFIndexSweepEngine().scan_all_indices(), failures, warnings)
    if mtf is not None:
        print(
            f"MTF status={mtf.get('status')} daily_coverage={mtf.get('scanned_indices')}/"
            f"{mtf.get('total_indices')} setups={len(mtf.get('setups', []))} "
            f"errors={len(mtf.get('errors', []))}"
        )
        if mtf.get("scanned_indices", 0) == 0:
            warnings.append("No MTF daily index histories were usable")
        for item in mtf.get("errors", [])[:5]:
            warnings.append(f"MTF {item.get('name')} {item.get('timeframe')}: {item.get('reason')}")

    print(f"\nELAPSED {time.monotonic() - started:.2f} sec")
    if failures:
        print("CRITICAL FAILURES:", *failures, sep="\n - ")
    if warnings:
        print("WARNINGS:", *warnings, sep="\n - ")
    if failures:
        return 1
    print("CRITICAL DIAGNOSTICS PASSED" if not warnings else "CRITICAL DIAGNOSTICS PASSED WITH FEED WARNINGS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
