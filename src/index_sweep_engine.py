"""Daily liquidity-sweep scanner for NSE indices (no constituent stocks)."""
import pandas as pd
import numpy as np
import yfinance as yf
from index_universe import INDEX_UNIVERSE, symbols_for_history


def _clean(df):
    if df is None or df.empty: return pd.DataFrame()
    x=df.copy()
    if isinstance(x.columns,pd.MultiIndex): x.columns=x.columns.get_level_values(0)
    return x.dropna(subset=["Open","High","Low","Close"]).sort_index()


class IndexSweepEngine:
    def __init__(self): self.indices_universe=INDEX_UNIVERSE
    def scan_all_indices(self,lookback_days=60): return self.scan_all_indices_sweeps(lookback_days)

    def scan_all_indices_sweeps(self,lookback_days=60):
        out=[]
        for item in self.indices_universe:
            used=None; df=pd.DataFrame()
            for sym in symbols_for_history(item):
                try:
                    q=_clean(yf.download(sym,period="6mo",interval="1d",progress=False,timeout=8))
                    if len(q)>=35: df,used=q,sym;break
                except Exception: pass
            if len(df)<35: continue
            r=self._analyze(df,item,used)
            if r and r["has_setup"]: out.append(r)
        return sorted(out,key=lambda x:x["score"],reverse=True)

    def _analyze(self,df,item,used):
        t,p=df.iloc[-1],df.iloc[-2]
        o,h,l,c=map(float,[t.Open,t.High,t.Low,t.Close]); rng=max(h-l,1e-9)
        wick=(min(o,c)-l)/rng
        delta=df.Close.diff(); gain=delta.clip(lower=0).rolling(14).mean(); loss=(-delta.clip(upper=0)).rolling(14).mean()
        rsi=100-100/(1+gain/loss.replace(0,np.nan)); rv=float(rsi.iloc[-1]) if np.isfinite(rsi.iloc[-1]) else 50.
        prior=df.iloc[-21:-1]; swing=float(prior.Low.min()); close_low=float(prior.Close.min())
        major=l<swing and c>swing and wick>=.30
        pdl=l<float(p.Low) and c>float(p.Low) and wick>=.35
        div=l<close_low and rv>(float(rsi.iloc[-15:-1].min()) if rsi.iloc[-15:-1].notna().any() else rv)+1.5 and rv<60
        fvg=l>float(df.High.iloc[-3]); ema20=float(df.Close.ewm(span=20,adjust=False).mean().iloc[-1]); above=c>=ema20
        score=0; conf=[]; level=swing
        # A rejection wick/divergence alone is not a liquidity sweep.
        if not (major or pdl): return {"name":item["name"],"has_setup":False}
        if major: score+=40;conf.append("Major Swing Low Swept & Reclaimed")
        elif pdl: score+=25;level=float(p.Low);conf.append("Prior Day Low Swept & Reclaimed")
        if wick>=.50: score+=20;conf.append("Massive 50%+ Lower-Wick Absorption")
        elif wick>=.35: score+=10;conf.append("Strong 35%+ Lower Rejection")
        if div:score+=20;conf.append("Bullish RSI Divergence")
        if fvg:score+=10;conf.append("Bullish Fair Value Gap")
        if above:score+=10;conf.append("Above 20 EMA")
        if score<35:return {"name":item["name"],"has_setup":False}
        grade="🔥 GRADE A+ SWEEP" if score>=70 else "⚡ GRADE B SWEEP" if score>=50 else "📈 GRADE C SWEEP"
        return {"name":item["name"],"ticker":used,"data_source":"actual_index" if used==item.get("index_symbol") else "index_tracking_etf",
            "category":item["category"],"description":item["description"],"current_price":round(c,2),"swept_level":round(level,2),
            "day_low":round(l,2),"lower_wick_pct":round(wick*100,1),"rsi":round(rv,1),"rsi_divergence":bool(div),
            "fvg_detected":bool(fvg),"fvg_top":round(l,2) if fvg else 0,"fvg_bottom":round(float(df.High.iloc[-3]),2) if fvg else 0,
            "above_20_ema":bool(above),"sweep_depth_pct":round(max(0,(level-l)/level*100),2),"quality_score":score,"score":score,
            "grade":grade,"tier_badge":grade,"confluences":conf,"has_setup":True,
            "action":f"Bullish index reversal watch; invalidation below {l*0.995:.2f}."}
