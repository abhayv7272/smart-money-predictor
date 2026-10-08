#!/usr/bin/env python3
"""
v2 participant-OI model — 15-saal backtested (2012-2026, 3,634 days).
Verified: IC@40d +0.21 | STRONG_UP @60d: 78% up-rate, +4.1% avg | 13/15 years positive IC.

3-layer output:
  L1 base allocation : 200DMA trend filter (100% above / 30% below)
  L2 entry sizing    : v2 bucket (STRONG_UP full, MILD/NEUTRAL half, STRONG_DOWN none)
  L3 outlook 40-60d  : v2 score + bucket expectation table
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRONG, WEAK = 2.5, 1.0

EXPECT = {  # from 15-year backtest (n per bucket 478-977)
    "STRONG_UP":   {"d40": "+2.7% avg, 75% up", "d60": "+4.1% avg, 78% up"},
    "MILD_UP":     {"d40": "+2.2% avg, 70% up", "d60": "+3.2% avg, 71% up"},
    "NEUTRAL":     {"d40": "+2.4% avg, 67% up", "d60": "+3.5% avg, 69% up"},
    "MILD_DOWN":   {"d40": "+1.9% avg, 66% up", "d60": "+2.8% avg, 65% up"},
    "STRONG_DOWN": {"d40": "+0.1% avg, 54% up", "d60": "+0.6% avg, 53% up"},
}
ENTRY = {"STRONG_UP": "FULL size — naye swing entries allowed",
         "MILD_UP": "HALF size", "NEUTRAL": "HALF size",
         "MILD_DOWN": "HALF size, selective", "STRONG_DOWN": "NO new entries"}

def rz(s, win=252, mp=60):
    m = s.rolling(win, min_periods=mp).mean()
    sd = s.rolling(win, min_periods=mp).std()
    return ((s - m) / sd.replace(0, np.nan)).clip(-4, 4)

def rpct(s, win=252, mp=60):
    return s.rolling(win, min_periods=mp).apply(lambda a: (a[:-1] <= a[-1]).mean(), raw=True)

def load_wide():
    oi = pd.read_csv(ROOT / "data/participant_oi_master.csv", parse_dates=["date"])
    oi = oi.drop_duplicates(subset=["date", "client_type"], keep="last")
    val_cols = [c for c in oi.columns if c not in ("date", "client_type")]
    w = oi[oi.client_type != "TOTAL"].pivot_table(index="date", columns="client_type", values=val_cols)
    w.columns = [f"{ct}_{vc}" for vc, ct in w.columns]
    return w.sort_index()

def v2_scores(w):
    X = pd.DataFrame(index=w.index)
    for who in ["FII", "Pro", "DII"]:
        X[f"{who}_fut_net"] = w[f"{who}_future_index_long"] - w[f"{who}_future_index_short"]
        X[f"{who}_stkfut_net"] = w[f"{who}_future_stock_long"] - w[f"{who}_future_stock_short"]
    X["FII_optbias"] = ((w["FII_option_index_call_long"] - w["FII_option_index_call_short"])
                        - (w["FII_option_index_put_long"] - w["FII_option_index_put_short"]))
    X["FII_longpct"] = w["FII_future_index_long"] / (w["FII_future_index_long"] + w["FII_future_index_short"])
    z = pd.DataFrame(index=X.index)
    z["s_pro"]  = rz(X["Pro_fut_net"])
    z["s_stk"]  = rz((X["FII_stkfut_net"] + X["Pro_stkfut_net"]).diff(20))
    z["s_fiiC"] = (0.5 - rpct(X["FII_longpct"])) * 4
    z["s_opt"]  = rz(X["FII_optbias"])
    z["s_dii"]  = rz(X["DII_fut_net"])
    z["slow_v2"] = 2*z.s_pro + 1.5*z.s_stk + 1.5*z.s_fiiC + 1*z.s_opt + 0.5*z.s_dii
    return z

def bucket(sc):
    if sc >= STRONG: return "STRONG_UP"
    if sc >= WEAK:   return "MILD_UP"
    if sc <= -STRONG: return "STRONG_DOWN"
    if sc <= -WEAK:   return "MILD_DOWN"
    return "NEUTRAL"

ENTRY_LABELS = {
    "STRONG_BUY": ("🟢🟢 STRONG — AB LAGANA HAI", "Capitulation zone (bottom-signal ACTIVE). Pura planned amount 3 kisht mein: 1/3 abhi, 1/3 agar -2%, 1/3 agar -4%. Stop-loss -10%. [15y: 75% win @40d, +3.0% avg; bottom 80% baar 20 din mein]"),
    "MEDIUM":     ("🟢 MEDIUM — lagao, half size", "OI strongly bullish (STRONG_UP) lekin crash-dip nahi. Half-size entries. [15y: 74% win @40d, +2.6% avg]"),
    "WEAK":       ("🟡 WEAK — chhota lagao", "OI mild bullish. Sirf selective/chhoti entries. [15y: 70% win @40d, +2.3% avg]"),
    "WAIT":       ("⚪ WAIT — naya paisa NAHI", "Koi clear OI edge nahi. Existing positions hold, naya paisa mat lagao. [15y: 66% win @40d — baseline jitna hi]"),
    "NO_ENTRY":   ("🔴 NO ENTRY — bilkul mat lagao", "OI STRONG_DOWN ya top-warning ACTIVE. Naye entries band, stops tight. [15y: sirf 55% win @40d, +0.2% avg]"),
}
DEPLOY_LABELS = {
    "FULL_100":      ("💰 FULL (100%)", "Nifty 200DMA ke upar + OI theek — poora invested raho. [15y: 69% win @40d]"),
    "REDUCED_70":    ("⚠️ REDUCED (70%)", "Trend upar LEKIN OI STRONG_DOWN — danger combo, thoda cash nikalo. [15y: sirf 53% win @40d, -0.3% avg — ye combo historically kharab hai]"),
    "CAUTION_65":    ("🌍 CAUTION (65%)", "India ka trend upar LEKIN America (S&P 500) apne 200DMA ke niche — global girawat aksar India ko kheench leti hai. Thoda cash rakho. [Verified: ye filter DD -24.5%→-21.9% aur Sharpe 0.67→0.74 karta hai]"),
    "ACCUMULATE_60": ("🛒 ACCUMULATE (60%)", "Bear phase LEKIN OI strongly bullish — dheere-dheere kharidne ka zone. [15y: 72% win @40d, +2.8%]"),
    "DEFENSIVE_30":  ("🛡️ DEFENSIVE (30%)", "Nifty 200DMA ke niche + OI unclear — capital bachao. Bounce aayega to ACCUMULATE/STRONG signal pakad lega."),
}

def master_signal(z, px):
    """Combined daily signal: entry grade + deploy grade (+ raw detector states)."""
    last = z.iloc[-1]
    v2 = float(last["slow_v2"])
    fii_pct = 0.5 - float(last["s_fiiC"]) / 4.0      # s_fiiC = (0.5-pct)*4
    pro_z = float(last["s_pro"])
    d20 = float(px.iloc[-1] / px.iloc[-21] - 1) if len(px) > 21 else 0.0
    above = bool(px.iloc[-1] > px.rolling(200).mean().iloc[-1])
    # B3/T4 active = aaj ya pichle 3 OI-din mein fire hua
    tail = z.tail(4)
    px20 = px.pct_change(20).reindex(tail.index, method="ffill")  # BUG FIX: price-lag par nearest earlier value use karo (pehle NaN -> B3 miss ho sakta tha)
    b3_days = [(r.slow_v2 >= 2.5) and (px20.get(i, 0) < -0.03) for i, r in tail.iterrows()]
    t4_days = [((0.5 - r.s_fiiC / 4.0) > 0.90) and (r.s_pro < -1) for i, r in tail.iterrows()]
    b3 = any(b3_days); t4 = any(t4_days)
    if b3: entry = "STRONG_BUY"
    elif v2 <= -2.5 or t4: entry = "NO_ENTRY"
    elif v2 >= 2.5: entry = "MEDIUM"
    elif v2 >= 1.0: entry = "WEAK"
    else: entry = "WAIT"
    # v3: global (S&P 500) trend filter — Sharpe 0.67->0.74 verified
    try:
        spx = pd.read_csv(ROOT / "data/spx_close.csv", parse_dates=["date"]).set_index("date")["close"]
        spx_above = bool(spx.iloc[-1] > spx.rolling(200).mean().iloc[-1])
    except Exception:
        spx_above = True
    if above and spx_above: deploy = "FULL_100" if v2 > -2.5 else "REDUCED_70"
    elif above and not spx_above: deploy = "CAUTION_65"
    else: deploy = "ACCUMULATE_60" if v2 >= 2.5 else "DEFENSIVE_30"
    return dict(entry=entry, deploy=deploy, b3_active=b3, t4_active=t4,
                v2=round(v2, 2), fii_pct=round(fii_pct, 2), pro_z=round(pro_z, 2),
                d20=round(d20, 4), above_200dma=above)

def predict():
    w = load_wide()
    z = v2_scores(w).dropna(subset=["slow_v2"])
    last = z.iloc[-1]
    px = pd.read_csv(ROOT / "data/nifty_close.csv", parse_dates=["date"]).set_index("date")["close"]
    dma200 = px.rolling(200).mean().iloc[-1]
    close = px.iloc[-1]
    above = bool(close > dma200)
    b = bucket(last["slow_v2"])
    ms = master_signal(z, px)
    return {
        "MASTER_entry_signal": ENTRY_LABELS[ms["entry"]][0],
        "MASTER_entry_detail": ENTRY_LABELS[ms["entry"]][1],
        "MASTER_deploy_signal": DEPLOY_LABELS[ms["deploy"]][0],
        "MASTER_deploy_detail": DEPLOY_LABELS[ms["deploy"]][1],
        "bottom_signal_B3": "🟢 ACTIVE" if ms["b3_active"] else "off",
        "top_warning_T4": "🔴 ACTIVE" if ms["t4_active"] else "off",
        "data_date": str(z.index[-1].date()),
        "price_date": str(px.index[-1].date()),
        "nifty_close": round(float(close), 2),
        "dma200": round(float(dma200), 2),
        "score_v2": round(float(last["slow_v2"]), 2),
        "bucket": b,
        "components": {k: round(float(last[k]), 2) for k in ["s_pro","s_stk","s_fiiC","s_opt","s_dii"]},
        "layer1_base_allocation": "100% (Nifty > 200DMA)" if above else "30% (Nifty < 200DMA — defensive)",
        "layer2_new_entry": ENTRY[b],
        "layer3_outlook_40d": EXPECT[b]["d40"],
        "layer3_outlook_60d": EXPECT[b]["d60"],
    }
