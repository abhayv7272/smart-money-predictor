"""Friday weekly liquidity-sweep scanner for NSE indices (no stocks)."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import yfinance as yf
from index_universe import INDEX_UNIVERSE, symbols_for_history


def _clean(df):
    if df is None or df.empty:return pd.DataFrame()
    x=df.copy()
    if isinstance(x.columns,pd.MultiIndex):x.columns=x.columns.get_level_values(0)
    return x.dropna(subset=["Open","High","Low","Close"]).sort_index()


def _weekly(d):
    return d.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()


def _swing_lows(w,n=2):
    a=w.Low.to_numpy(float);m=np.zeros(len(a),bool)
    for i in range(n,len(a)-n):m[i]=a[i]<=a[i-n:i].min() and a[i]<a[i+1:i+n+1].min()
    return m


class WeeklyIndexSweepEngine:
    def __init__(self):self.indices_universe=INDEX_UNIVERSE
    def is_friday(self):return datetime.now(ZoneInfo("Asia/Kolkata")).weekday()==4
    def scan_weekly_indices(self,lookback_weeks=52):
        hits=[];near=[];fail=[]
        for item in self.indices_universe:
            used=None;d=pd.DataFrame()
            for sym in symbols_for_history(item):
                try:
                    q=_clean(yf.download(sym,period="2y",interval="1d",progress=False,timeout=8))
                    if len(q)>=150:d,used=q,sym;break
                except Exception:pass
            if len(d)<150:fail.append(item["name"]);continue
            bars=_weekly(d)
            # Never score a still-forming weekly candle; Friday 21:00 IST includes the closed week.
            if not self.is_friday() and len(bars): bars=bars.iloc[:-1]
            r=self._evaluate(bars,item,used)
            if r:
                (hits if r["has_setup"] else near).append(r)
        hits.sort(key=lambda x:x["score"],reverse=True)
        return {"total_scanned":len(self.indices_universe),"weekly_hits":hits,"near_misses":near,
                "failed_indices":fail,"scan_date":datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat(),"is_friday":self.is_friday()}

    def _evaluate(self,w,item,used):
        if len(w)<30:return None
        i=len(w)-1;o,h,l,c=map(float,[w.Open.iloc[i],w.High.iloc[i],w.Low.iloc[i],w.Close.iloc[i]])
        rng=max(h-l,1e-9);body=abs(c-o);lower=min(o,c)-l;wick=lower/rng;closepos=(c-l)/rng
        mask=_swing_lows(w);start=max(0,i-26); pools=[]
        for j in np.flatnonzero(mask):
            if start<=j<i:pools.append((float(w.Low.iloc[j]),"Fractal Swing Low"))
        pools += [(float(w.Low.iloc[start:i].min()),"26-Week Low"),(float(w.Low.iloc[max(0,i-52):i].min()),"52-Week Low")]
        swept=[(lev,typ) for lev,typ in pools if l<lev and c>lev and .004<=(lev-l)/lev<=.16]
        if not swept:return None
        lev,typ=min(swept,key=lambda z:z[0]);depth=(lev-l)/lev*100
        delta=w.Close.diff();g=delta.clip(lower=0).rolling(14).mean();loss=(-delta.clip(upper=0)).rolling(14).mean();rs=g/loss.replace(0,np.nan)
        rsi=100-100/(1+rs);rv=float(rsi.iloc[-1]) if np.isfinite(rsi.iloc[-1]) else 50
        div=c<float(w.Close.iloc[-15:-1].min()) and rv>(float(rsi.iloc[-15:-1].min()) if rsi.iloc[-15:-1].notna().any() else rv)+1.5
        sma20=float(w.Close.rolling(20).mean().iloc[-1]);above=c>=sma20
        score=25;conf=[f"{typ} Swept & Reclaimed ({depth:.2f}%)"]
        if wick>=.5:score+=25;conf.append("50%+ Weekly Hammer Wick")
        elif wick>=.35:score+=15;conf.append("35%+ Weekly Rejection")
        if closepos>=.65:score+=15;conf.append("Close in Upper 35%")
        elif closepos>=.5:score+=10;conf.append("Close in Upper Half")
        if div:score+=15;conf.append("Weekly Bullish RSI Divergence")
        if above:score+=10;conf.append("Above Weekly 20 SMA")
        if c>=o:score+=10;conf.append("Green Weekly Candle")
        valid=wick>=.34 and lower>=1.15*body and closepos>=.5 and score>=40
        grade="🔥 WEEKLY GRADE A+ SWEEP" if score>=70 else "⚡ WEEKLY GRADE B SWEEP" if score>=50 else "📈 WEEKLY GRADE C SWEEP"
        return {"name":item["name"],"ticker":used,"data_source":"actual_index" if used==item.get("index_symbol") else "index_tracking_etf",
            "category":item["category"],"description":item["description"],"current_price":round(c,2),"weekly_low":round(l,2),"day_low":round(l,2),
            "swept_level":round(lev,2),"pool_type":typ,"sweep_depth_pct":round(depth,2),"wick_pct":round(wick*100,1),
            "lower_wick_pct":round(wick*100,1),"close_in_range_pct":round(closepos*100,1),"rsi":round(rv,1),"rsi_divergence":bool(div),
            "above_20_sma":bool(above),"is_green":bool(c>=o),"score":score,"quality_score":score,"grade":grade,"tier_badge":grade,
            "confluences":conf,"has_setup":valid,"is_near_miss":not valid,"target_horizon":"2 to 6 Weeks","stop_loss_level":round(l*.99,2)}
