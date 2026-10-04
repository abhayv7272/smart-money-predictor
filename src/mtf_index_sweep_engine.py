"""Index-only adaptation of the Colab MTF BUY-side sweep/MSS framework.

Source notebook: /home/user/colab_source_1b1X77M9WfsDdcEvcJb8UKP5EuV333k2r.ipynb
No equity symbol universe is used. The engine scans NSE index symbols only.
"""
from __future__ import annotations
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Dict, Optional, Tuple, List
import numpy as np
import pandas as pd
import yfinance as yf
from index_universe import INDEX_UNIVERSE, symbols_for_history

SWING_WINDOW = 2
SL_BUFFER_PCT = 0.002
MIN_RR_T2 = 1.0

def _flat(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    x = df.copy()
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = x.columns.get_level_values(0)
    idx = pd.to_datetime(x.index, errors="coerce")
    good = ~pd.isna(idx)
    x = x.loc[good].copy(); idx = idx[good]
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("Asia/Kolkata").tz_localize(None)
    x.index = pd.DatetimeIndex(idx)
    return x[~x.index.duplicated(keep="last")].sort_index()


def _ref_date() -> date:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.weekday() == 5: return (now - timedelta(days=1)).date()
    if now.weekday() == 6: return (now - timedelta(days=2)).date()
    if (now.hour, now.minute) < (15, 30):
        now -= timedelta(days=1)
        while now.weekday() >= 5: now -= timedelta(days=1)
    return now.date()


def _weekly_levels(daily: pd.DataFrame, ref: date) -> Tuple[Optional[float], Optional[float]]:
    x = _flat(daily); x = x[x.index.date <= ref]
    if len(x) < 10: return None, None
    wk = x.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
    if len(wk) < 2: return None, None
    return float(wk.iloc[-2].High), float(wk.iloc[-2].Low)


def _current_week(df: pd.DataFrame, ref: date) -> pd.DataFrame:
    x = _flat(df); monday = ref - timedelta(days=ref.weekday())
    return x[(x.index.date >= monday) & (x.index.date <= ref)]


def _swing_highs(df: pd.DataFrame, n: int = 2) -> List[int]:
    out=[]
    for i in range(n, len(df)-n):
        h=float(df.High.iloc[i])
        if np.all(h > df.High.iloc[i-n:i].values) and np.all(h > df.High.iloc[i+1:i+n+1].values): out.append(i)
    return out


class MTFIndexSweepEngine:
    """Previous-week PWL -> daily reclaim -> causal current-week 15m bullish MSS."""
    def scan_all_indices(self) -> Dict[str, object]:
        ref = _ref_date(); results=[]; errors=[]
        for item in INDEX_UNIVERSE:
            name, category = item["name"], item["category"]
            ticker = None
            try:
                daily = pd.DataFrame()
                for candidate in symbols_for_history(item):
                    probe = _flat(yf.download(candidate, period="6mo", interval="1d", progress=False, timeout=8))
                    if len(probe) >= 30:
                        daily, ticker = probe, candidate
                        break
                if len(daily) < 30: continue
                pwh,pwl = _weekly_levels(daily, ref)
                if pwh is None: continue
                cur = _current_week(daily, ref)
                if cur.empty: continue
                week_low=float(cur.Low.min()); close=float(cur.Close.iloc[-1])
                # Notebook's unchanged BUY-only daily trap.
                if not (week_low < pwl and close > pwl): continue
                active = cur.Low.cummin().lt(pwl) & cur.Close.gt(pwl)
                starts = active & ~active.shift(1, fill_value=False)
                pos=np.flatnonzero(starts.to_numpy())
                if not len(pos): continue
                confirm=cur.index[int(pos[-1])].normalize()+pd.Timedelta(hours=15,minutes=30)
                row={"name":name,"ticker":ticker,"data_source":"actual_index" if ticker==item.get("index_symbol") else "index_tracking_etf", "category":category,"status":"DAILY_TRAP_CONFIRMED",
                     "pwh":round(pwh,2),"pwl":round(pwl,2),"week_low":round(week_low,2),
                     "latest_close":round(close,2),"trap_confirmation_time":str(confirm),
                     "entry":None,"stoploss":None,"target_1":None,"target_2":round(pwh,2),
                     "rr_t2":None,"mss_time":None,"fresh_trigger":False}
                intraday=_flat(yf.download(ticker,period="10d",interval="15m",progress=False,timeout=8))
                monday=pd.Timestamp(ref-timedelta(days=ref.weekday())); end=pd.Timestamp(ref)+pd.Timedelta(days=1)
                if not intraday.empty:
                    regular=(intraday.index.time>=pd.Timestamp("09:15").time())&(intraday.index.time<pd.Timestamp("15:30").time())
                    intraday=intraday[(intraday.index>=monday)&(intraday.index<end)&regular]
                if len(intraday)<20:
                    row["status"]="PENDING_15M_DATA"; results.append(row); continue
                z=intraday.reset_index(); z.rename(columns={z.columns[0]:"_Time"},inplace=True)
                mask=z.Low<pwl
                if not mask.any(): row["status"]="PENDING_MSS"; results.append(row); continue
                extreme_pos=int(z.loc[mask,"Low"].idxmin()); trough=float(z.loc[extreme_pos,"Low"])
                swings=_swing_highs(z.iloc[:extreme_pos+1],SWING_WINDOW)
                if not swings: row["status"]="PENDING_SWING_STRUCTURE"; results.append(row); continue
                swing_pos=swings[-1]; trigger=float(z.loc[swing_pos,"High"]); sl=trough*(1-SL_BUFFER_PCT)
                risk=trigger-sl; t1=trigger+risk
                post=z.iloc[extreme_pos+1:]; post=post[post._Time>confirm]; hit=post.Close>trigger
                row.update(entry=round(trigger,2),stoploss=round(sl,2),target_1=round(t1,2),target_2=round(pwh,2),
                           rr_t2=round((pwh-trigger)/risk,2) if risk>0 else None)
                if hit.any():
                    mss_pos=int(post.loc[hit].index[0]); mss_time=pd.Timestamp(z.loc[mss_pos,"_Time"])
                    row.update(status="TRIGGERED_ACTIVE" if row["rr_t2"] is not None and row["rr_t2"]>=MIN_RR_T2 else "FILTERED_LOW_RR",
                               mss_time=str(mss_time),mss_close=round(float(z.loc[mss_pos,"Close"]),2),
                               fresh_trigger=(mss_time.date()==ref))
                else: row["status"]="PENDING_MSS"
                results.append(row)
            except Exception as e: errors.append(f"{ticker}: {e}")
        actionable=[r for r in results if r["status"] in ("TRIGGERED_ACTIVE","PENDING_MSS","DAILY_TRAP_CONFIRMED")]
        triggered=[r for r in results if r["status"]=="TRIGGERED_ACTIVE"]
        return {"reference_date":str(ref),"total_indices":len(INDEX_UNIVERSE),"setups":results,
                "actionable":actionable,"triggered":triggered,"has_signals":bool(actionable),"errors":errors}
