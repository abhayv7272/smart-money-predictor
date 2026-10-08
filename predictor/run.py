#!/usr/bin/env python3
"""Daily runner: fetch latest OI -> update Nifty close -> predict -> SIMPLE Hinglish report."""
import json, datetime as dt
from pathlib import Path
import pandas as pd

import fetch_oi
from model import predict

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"; OUT.mkdir(exist_ok=True)

def sweep_scan_section():
    """Index sweep scanner: saare NSE indices par liquidity-sweep setups + charts.
    Fail-safe: koi bhi error aaye to report ke baki hisse kharab na ho."""
    extras = {"drows": [], "wrows": [], "chart_files": []}
    try:
        import fetch_indices
        fetch_indices.update_indices(lookback_days=7)
    except Exception as e:
        print(f"[sweep] indices update fail ({e}) — using existing data")
    try:
        from index_screener import screen, markdown_section
        cdir = OUT / "charts"
        # purane charts hatao (sirf aaj ke setups rakho)
        if cdir.exists():
            for old in cdir.glob("sweep_*.png"):
                old.unlink()
        setups, charts, latest, ranks = screen(str(ROOT / "data/indices_ohlc.csv"),
                                               chart_dir=str(cdir), top_charts=5)
        md = markdown_section(setups, charts, latest, ranks, chart_relpath="charts")
        extras["chart_files"] += [("🧲 Daily sweep: " + c[0], c[1]) if isinstance(c, tuple) else ("🧲 Daily sweep setup", c) for c in charts[:1]]
    except Exception as e:
        print(f"[sweep] daily scanner fail: {e}")
        md, setups = "", []
    # WEEKLY scanner (zyada strong signal — user request #2)
    try:
        from weekly_index_screener import screen_weekly, markdown_section_weekly
        cdir = OUT / "charts"
        if cdir.exists():
            for old in cdir.glob("wsweep_*.png"):
                old.unlink()
        wsetups, wcharts, wlatest, wforming = screen_weekly(
            str(ROOT / "data/indices_ohlc.csv"), chart_dir=str(cdir), top_charts=5)
        wmd = markdown_section_weekly(wsetups, wcharts, wlatest,
                                      chart_relpath="charts", forming=wforming)
        extras["chart_files"] += [("📅 Weekly sweep: " + c[0], c[1]) if isinstance(c, tuple) else ("📅 Weekly sweep setup", c) for c in wcharts[:1]]
        if wmd:
            md = (md + "\n\n---\n\n" + wmd) if md else wmd
    except Exception as e:
        print(f"[sweep] weekly scanner fail: {e}")
        wsetups = []
    # SWEEP REPORT CARD — pichle 1-2 hafte ke setups track karo (user request)
    try:
        from sweep_tracker import track_daily, track_weekly, markdown_tracking
        cdir = OUT / "charts"
        if cdir.exists():
            for old in list(cdir.glob("track_*.png")) + list(cdir.glob("wtrack_*.png")):
                old.unlink()
        drows, dcharts, _ = track_daily(str(ROOT / "data/indices_ohlc.csv"),
                                        days=10, chart_dir=str(cdir), max_charts=4)
        wrows, twcharts = track_weekly(str(ROOT / "data/indices_ohlc.csv"),
                                      weeks=3, chart_dir=str(cdir), max_charts=3)
        tmd = markdown_tracking(drows, dcharts, wrows, twcharts, chart_relpath="charts")
        extras["drows"], extras["wrows"] = drows, wrows
        extras["chart_files"] += [("📋 Report card: " + c[0], c[1]) if isinstance(c, tuple) else ("📋 Report card tracking", c) for c in dcharts[:1]]
        if tmd:
            md = (md + "\n\n---\n\n" + tmd) if md else tmd
    except Exception as e:
        print(f"[sweep] tracker fail: {e}")
    return md, setups, wsetups, extras

def update_prices():
    f = ROOT / "data/nifty_close.csv"
    px = pd.read_csv(f, parse_dates=["date"])
    try:
        import yfinance as yf
        start = (px["date"].max() + pd.Timedelta(days=1)).date()
        # BUG FIX: agar data already up-to-date hai to yfinance ko future-date call mat karo
        if start > dt.date.today():
            raise StopIteration("already up to date")
        new = yf.download("^NSEI", start=str(start), progress=False, auto_adjust=False)
        if len(new):
            new = new[["Close"]].reset_index()
            new.columns = ["date", "close"]
            new = new.dropna()
            px = pd.concat([px, new]).drop_duplicates(subset=["date"], keep="last").sort_values("date")
            px.to_csv(f, index=False)
            print(f"[price] updated to {px['date'].max().date()}")
    except StopIteration:
        print("[price] already up to date")
    except Exception as e:
        print(f"[price] yfinance fail ({e}) — using existing prices")
    # SPX bhi update karo (global filter ke liye)
    try:
        import yfinance as yf
        f2 = ROOT / "data/spx_close.csv"
        sp = pd.read_csv(f2, parse_dates=["date"])
        s2 = (sp["date"].max() + pd.Timedelta(days=1)).date()
        if s2 > dt.date.today():
            raise StopIteration("spx up to date")
        new = yf.download("^GSPC", start=str(s2), progress=False, auto_adjust=False)
        if len(new):
            new = new[["Close"]].reset_index(); new.columns=["date","close"]
            sp = pd.concat([sp, new.dropna()]).drop_duplicates(subset=["date"], keep="last").sort_values("date")
            sp.to_csv(f2, index=False)
    except StopIteration:
        print("[spx] already up to date")
    except Exception as e:
        print(f"[spx] update fail ({e})")

# ---------- SIMPLE LANGUAGE (noob-friendly) ----------
SIMPLE = {
    "STRONG": {
        "emoji": "🟢🟢",
        "one_liner": "Market gir ke sasta hua hai aur bade khiladi (operators/FII) chupke se KHARID rahe hain — naya swing trade shuru karne ka SABSE ACHHA mauka. Aise mauke saal mein sirf 2-3 baar aate hain.",
        "kya_karna": [
            "Jitna paisa is trade ke liye socha hai, usse 3 hisson mein baanto",
            "Pehla hissa (1/3) AAJ/KAL kharido (Nifty 50 index fund / NIFTYBEES)",
            "Dusra hissa tab kharido agar market 2% aur gire",
            "Teesra hissa tab agar 4% aur gire — girna accha hai, aur sasta milega!",
            "Har kharid par likh lo: 'agar meri kharid se 8% niche gaya to bech dunga' — ye wada khud se karo",
        ],
        "accuracy": "Pichle 15 saal mein ye signal 40 baar aaya — 10 mein se 8 baar market 20 din ke andar bottom bana ke upar gaya.",
    },
    "MEDIUM": {
        "emoji": "🟢",
        "one_liner": "Bade khiladi bullish hain (kharid rahe hain), lekin market abhi sasta nahi hua. Trade kar sakte ho, par AADHA paisa hi lagao.",
        "kya_karna": [
            "Jo amount socha tha uska sirf AADHA (50%) lagao",
            "2 kisht mein: aadha abhi, aadha agar market 2% gire",
            "-10% stop-loss ka niyam yahan bhi pakka",
        ],
        "accuracy": "Aise dino ke baad 10 mein se ~7.5 baar market 2 mahine mein upar tha (avg +3.6%).",
    },
    "WEAK": {
        "emoji": "🟡",
        "one_liner": "Halka sa bullish mahaul hai, par koi strong signal nahi. Bahut chhota trade karo, ya skip karke behtar mauke ka wait karo.",
        "kya_karna": [
            "Max apne planned amount ka 25% hi lagao — ya bilkul mat lagao, koi jaldi nahi",
            "Naye bande ke liye behtar: SKIP karo, STRONG/MEDIUM signal ka wait karo",
        ],
        "accuracy": "10 mein se ~7 baar positive, lekin edge chhota hai — isliye chhota size.",
    },
    "WAIT": {
        "emoji": "⚪",
        "one_liner": "Aaj koi khaas signal NAHI hai. Naya paisa lagane ka din nahi — jo trade pehle se chal rahe hain unhe chalne do, naya kuch mat karo.",
        "kya_karna": [
            "Naya trade: NAHI (patience bhi trading hai!)",
            "Purane trades: hold karo, unka stop-loss check kar lo",
            "Roz ye report dekhte raho — signal aane par batayega",
        ],
        "accuracy": "Aise dino mein market ka result bilkul average hota hai — koi fayda nahi jaldi karne ka.",
    },
    "NO": {
        "emoji": "🔴",
        "one_liner": "KHATRA zone — bade khiladi bech rahe hain ya market top ke paas lag raha hai. Naya paisa BILKUL mat lagao. Jo profit bana hai usko bachane ka waqt hai.",
        "kya_karna": [
            "Naya trade: BILKUL NAHI — chahe kitna bhi mann kare",
            "Jo trades profit mein hain: thoda profit book kar lo (aadha bech do)",
            "Jo loss mein hain: stop-loss aur tight karo (-5%)",
            "Cash jama karo — jab STRONG signal aayega tab kaam aayega",
        ],
        "accuracy": "Aise dino ke baad market 10 mein se sirf 5.5 baar upar gaya — yaani coin-flip se bhi bura. Paisa lagane ka koi matlab nahi.",
    },
}
DEPLOY_SIMPLE = {
    100: ("India aur America dono ka trend UPAR hai aur bade khiladi theek hain", "pura invested reh sakte ho"),
    65:  ("India ka trend upar hai LEKIN America (S&P 500) girawat mein hai — global girawat India ko bhi kheenchti hai", "thoda cash mein rakho"),
    70:  ("Trend upar hai LEKIN bade khiladi zor se BECH rahe hain — ye combo historically kharab hai", "thoda paisa nikal ke cash mein rakho"),
    60:  ("Market girawat mein hai LEKIN bade khiladi kharid rahe hain — dheere-dheere jama karne ka zone", "aadhe se thoda zyada invested raho, girawat par kharidte raho"),
    30:  ("Market ka trend NEECHE hai (Nifty apni 200-din ki average se niche)", "zyada paisa cash mein rakho, sirf thoda market mein"),
}


# ---------- HORIZON OUTLOOK (15-saal backtest: har bucket x har horizon; entry T+1) ----------
# Source: v2 buckets par 3,538 din ke forward returns (verified is chat mein).
# 1 din / 1 hafta: KISI bucket mein edge NAHI (STRONG_UP bhi baseline jitna) -> prediction NAHI dete.
HORIZON_STATS = {
    # bucket: (4d avg, 4d %up, 15d avg, 15d %up, 1 mahina avg, %up, 2 mahine avg, %up)
    # 15y full-period, T+1 entry. 15d chuna gaya (10d nahi) kyunki curve-test mein 15d par
    # bearish edge ~2x strong (SD IS -0.63/OOS -0.87pp) aur SU-SD spread dono periods +ve.
    "STRONG_UP":   (+0.18, 57, +0.77, 59, +1.20, 63, +4.19, 79),
    "MILD_UP":     (+0.16, 57, +0.87, 65, +1.10, 69, +3.39, 71),
    "NEUTRAL":     (+0.33, 58, +1.19, 63, +1.40, 66, +3.60, 69),
    "MILD_DOWN":   (+0.28, 57, +1.04, 64, +1.39, 66, +2.95, 65),
    "STRONG_DOWN": (+0.04, 52, -0.01, 52, -0.01, 51, +0.72, 53),
}
HORIZON_BASE = (+0.19, 56, +0.73, 60, +0.98, 62, +2.99, 68)   # baseline (sab din)

def fast_pulse():
    """⚡ Short-term pulse — 15-saal battery test (train 2012-19 / test 2020-26) mein
    sirf 2 cheezein DONO periods mein pass hui:
    (1) PRO-DUMP bounce: Pro ka index-fut net 1-din change z<-1.0 (252d) →
        agle 1-3 din halka bullish jhukav (1d edge IS +0.08pp / OOS +0.16pp;
        1d win% 12/14 saal baseline se behtar). z<-2.0 → 5d edge bhi (+0.34/+0.37pp).
    (2) VIX DAR-ZONE: India VIX 252d percentile >80 → 1-mahina historically behtar
        (20d edge +0.68/+0.83pp, win 66-69% dono halves; bull bucket ke saath aur strong).
    (3) GAMMA SQUEEZE: monthly expiry ke aakhri 3 din AND Pro options-net z<-1.5
        (Pro short-gamma heavy) → agle 5 din bounce (5d edge IS +0.27 / OOS +0.90pp,
        win +6/+14pp, 9/11 saal positive, ~8 fire/saal).
    REJECTED (dono periods mein fail — dobara mat jodo): INR-crash (sirf 2020 ka tha),
    RSI2 extremes, SPX-kal, 3-din-laal, breadth, Monday/Friday, composite ST score,
    VWAP family (rolling/anchored/cross/deviation — sab fail), Retail option-hog
    (sirf 5/14 saal), ProGamma-short alone (8/13 saal, thin).
    Fail-safe: koi bhi error → neutral pulse, report kharab nahi hogi."""
    pulse = {"pro_dump": False, "pro_flush_big": False, "zpro": None,
             "vix_fear": False, "vix_pctl": None,
             "gamma_squeeze": False, "zgam": None, "dte": None}
    try:
        from model import load_wide
        w = load_wide()
        pro = w["Pro_future_index_long"] - w["Pro_future_index_short"]
        d = pro.diff()
        zz = float(((d - d.rolling(252).mean()) / d.rolling(252).std()).iloc[-1])
        pulse["zpro"] = round(zz, 2)
        pulse["pro_dump"] = zz < -1.0
        pulse["pro_flush_big"] = zz < -2.0
    except Exception as e:
        print(f"[pulse] pro-dump calc fail: {e}")
    try:
        import calendar
        from model import load_wide
        w = load_wide()
        gam = ((w["Pro_option_index_call_long"] + w["Pro_option_index_put_long"])
               - (w["Pro_option_index_call_short"] + w["Pro_option_index_put_short"]))
        zg = float(((gam - gam.rolling(252).mean()) / gam.rolling(252).std()).iloc[-1])
        pulse["zgam"] = round(zg, 2)
        d = pd.Timestamp(w.index[-1])
        last_thu = max(wk[3] for wk in calendar.monthcalendar(d.year, d.month) if wk[3])
        exp = pd.Timestamp(d.year, d.month, last_thu)
        if d > exp:
            y2, m2 = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
            last_thu = max(wk[3] for wk in calendar.monthcalendar(y2, m2) if wk[3])
            exp = pd.Timestamp(y2, m2, last_thu)
        dte = (exp - d).days
        pulse["dte"] = int(dte)
        pulse["gamma_squeeze"] = (dte <= 3) and (zg < -1.5)
    except Exception as e:
        print(f"[pulse] gamma-squeeze calc fail: {e}")
    try:
        df = pd.read_csv(ROOT / "data/indices_ohlc.csv", parse_dates=["Date"])
        v = (df[df["Index"].str.contains("VIX", case=False, na=False)]
             .sort_values("Date")["Close"].astype(float))
        if len(v) >= 120:                     # kam se kam ~6 mahine ka history
            win = v.tail(252)
            pct = float((win < win.iloc[-1]).mean() * 100)
            pulse["vix_pctl"] = round(pct)
            pulse["vix_fear"] = pct > 80
    except Exception as e:
        print(f"[pulse] vix calc fail: {e}")
    return pulse

def horizon_section(bucket_name, pulse=None):
    st = HORIZON_STATS.get(bucket_name)
    if not st:
        return "", {}
    pulse = pulse or {}
    d4a, d4w, d15a, d15w, m1a, m1w, m2a, m2w = st
    bd4a, bd4w, bd15a, bd15w, b1a, b1w, b2a, b2w = HORIZON_BASE
    def vs(x, b):
        d = x - b
        return f"{'baseline se BEHTAR' if d > 0.3 else 'baseline se KHARAB' if d < -0.3 else 'baseline jitna hi'}"
    # ⚡ FAST PULSE — sirf test-pass cheezein (dekho fast_pulse() docstring)
    zp = pulse.get("zpro")
    d1_extra = w1_extra = m1_extra = ""
    p1d = p1m = ""
    if pulse.get("pro_dump"):
        d1_extra = (f" ⚡ **PAR AAJ exception fire hua:** Pro ne aaj ek hi din mein bhaari "
                    f"betting kaati (z={zp}). 15 saal mein aise din ke baad agla din "
                    f"**12/14 saal** average se behtar raha — halka BOUNCE jhukav. "
                    f"(Hint hai, guarantee nahi — position sizing mat badlo.)")
        p1d = f"⚡ Pro-flush bounce (z={zp})"
    w1_extra = d15_extra = ""
    pd4 = pd15 = ""
    if pulse.get("pro_dump"):
        w1_extra += (f" ⚡ **Aaj Pro-flush fire hua (z={zp})** — bounce jhukav 1-4 din tak bhi "
                     f"tested hai (4d edge +0.17/+0.33pp dono test-periods).")
        pd4 = f"⚡ Pro-flush bounce (z={zp})"
    if pulse.get("pro_flush_big"):
        w1_extra += (" ⚡ **Flush BAHUT bada tha (z<-2)** — aisa saal mein ~6 baar hota hai; "
                     "2 hafte tak bounce jhukav (4d +0.5pp, 10d +0.4/+0.8pp dono periods). "
                     "Phir bhi: jhukav hai, trade ka licence nahi.")
        pd15 = "⚡ Bada Pro-flush — 2 hafte tak bounce jhukav"
    if pulse.get("gamma_squeeze"):
        w1_extra += (f" 🌀 **GAMMA SQUEEZE setup:** monthly expiry {pulse.get('dte')} din door, "
                     f"Pro options mein bhaari SHORT-gamma (z={pulse.get('zgam')}). 15 saal mein aise "
                     f"expiry-hafton ke baad agle 4-10 din **9/11 saal** behtar rahe (test-period "
                     f"4d +0.6pp / 10d +0.9pp) — naye series mein squeeze-bounce jhukav.")
        pd4 = (pd4 + " + " if pd4 else "") + f"🌀 Gamma-squeeze (expiry {pulse.get('dte')}d)"
        pd15 = (pd15 + " + " if pd15 else "") + "🌀 Gamma-squeeze bounce"
    sd15_warn = ""
    if bucket_name == "STRONG_DOWN":
        sd15_warn = (" 🔻 **Dhyan do: STRONG_DOWN ka 15-din edge ASLI hai** — 15 saal mein dono "
                     "test-periods kamzor (IS -0.6pp / OOS -0.9pp, 52% vs 60% baseline). Agle "
                     "2-3 hafte naya paisa lagane ki jaldi mat karo.")
        pd15 = (pd15 + " + " if pd15 else "") + "🔻 15-din kamzori signal"
    if pulse.get("vix_fear"):
        vp = pulse.get("vix_pctl")
        m1_extra = (f" 🔥 **Bonus aaj:** India VIX dar-zone mein hai (saal ka top {100-int(vp)}% "
                    f"— percentile {vp}). 15 saal mein jab dar itna zyada tha, agla 1 mahina "
                    f"historically **aur behtar** nikla (+0.7-0.8pp extra, 66-69% baar up).")
        p1m = f"🔥 VIX dar-zone (pctl {pulse.get('vix_pctl')}) — 1m historically behtar"
    md = f"""## 🔭 AAGE KA NAZARIYA (aaj ke OI signal ke baad kya hota aaya hai — 15 saal ka hisaab)

| Kitne time baad | Kya expect karein | Imandar sach |
|---|---|---|
| **Kal (1 din)** | {'⚡ Halka bounce jhukav' if pulse.get('pro_dump') else '🚫 Prediction NAHI'} | Humne 15 saal test kiya — agle din ka koi bhi signal **coin-flip** hai (53% up, har bucket mein same). Jo bhi "kal ye hoga" bole, usse door raho.{d1_extra} |
| **1-4 din** | {('⚡ Halka bounce jhukav' if (pulse.get('pro_dump') or pulse.get('gamma_squeeze')) else f'{d4a:+.1f}% avg, {d4w}% baar upar')} | Bucket se 1-4 din ka koi bharosemand edge NAHI (aaj ka bucket {d4a:+.1f}%/{d4w}% vs baseline {bd4a:+.1f}%/{bd4w}% — farak na ke barabar). Sirf ⚡/🌀 flags fire hone par halka jhukav banta hai.{w1_extra} |
| **15 din (3 hafte)** | {('🔻 Kamzori ka signal' if bucket_name=='STRONG_DOWN' else f'{d15a:+.1f}% avg, {d15w}% baar upar')} | Aaj ka bucket: {d15a:+.1f}%/{d15w}% vs baseline {bd15a:+.1f}%/{bd15w}%. Yahan se signal jaagna shuru hota hai (curve-test: 15d par bearish edge pakki, bullish edge 20d+ se) — par asli kaam 20-60 din mein hi hota hai.{sd15_warn}{d15_extra} |
| **1 mahina (20 din)** | {m1a:+.1f}% avg, **{m1w}% baar upar** | {vs(m1a, b1a)} (baseline {b1a:+.1f}%/{b1w}%). Halka edge shuru hota hai.{m1_extra} |
| **2 mahine (40-60 din)** | {m2a:+.1f}% avg, **{m2w}% baar upar** | {vs(m2a, b2a)} (baseline {b2a:+.1f}%/{b2w}%). **YAHI is system ka asli edge hai** — isliye swing hold 1-2 mahine ka hai. |

> 💡 **Matlab:** aaj entry lo to result ka asli test **1-2 mahine baad** hona hai. Beech ke din-hafte ka shor ignore karo — stop-loss (-10%) ke alawa koi reaction mat do.
"""
    em = dict(m1=f"{m1a:+.1f}% / {m1w}% up", m2=f"{m2a:+.1f}% / {m2w}% up",
              m1w=m1w, m2w=m2w, m1a=m1a, m2a=m2a,
              d4a=d4a, d4w=d4w, d15a=d15a, d15w=d15w,
              sd15=(bucket_name == "STRONG_DOWN"),
              p1d=p1d, pd4=pd4, pd15=pd15, p1m=p1m)
    return md, em


# ---- BANK NIFTY (Addition v18-B): same v2 signal, BNF par 15y verified stats ----
# (bucket: d15a,d15w, m1a,m1w, m2a,m2w) | STRONG_UP @2m OOS +3.82%/79%; STRONG_DOWN clearly flat/neg
BNF_STATS = {
    "STRONG_UP":   (1.06, 60, 1.52, 62, 3.36, 75),
    "MILD_UP":     (1.20, 62, 1.54, 64, 2.72, 66),
    "NEUTRAL":     (1.29, 60, 1.53, 60, 2.82, 63),
    "MILD_DOWN":   (1.28, 61, 1.79, 62, 2.77, 62),
    "STRONG_DOWN": (-0.02, 51, 0.00, 51, 0.36, 53),
}
BNF_BASE = (0.92, 58, 1.22, 59, 2.40, 64)

def bnf_section(bucket_name):
    """Bank Nifty mini-section — fail-safe ("", {})."""
    try:
        df = pd.read_csv(ROOT / "data/indices_ohlc.csv", parse_dates=["Date"])
        b = df[df["Index"] == "Nifty Bank"].sort_values("Date")
        if len(b) < 2:
            return "", {}
        last, prev = b.iloc[-1], b.iloc[-2]
        chg = (last["Close"] / prev["Close"] - 1) * 100
        d15a, d15w, m1a, m1w, m2a, m2w = BNF_STATS.get(bucket_name, BNF_BASE)
        b15a, b15w, b1a, b1w, b2a, b2w = BNF_BASE
        sd = bucket_name == "STRONG_DOWN"
        warn = ""
        if sd:
            warn = ("\n> 🔻 **BNF par bhi wahi kahani:** STRONG_DOWN mein Bank Nifty 2 mahine tak "
                    "lagbhag flat/negative raha hai (baseline +2.4% chhodo) — BANKBEES entry se bhi door raho.")
        md = f"""## 🏦 BANK NIFTY — WAHI SIGNAL, DUSRA INDEX (15-saal verified)

**Aaj:** Bank Nifty **{last['Close']:,.0f}** ({chg:+.2f}% din ka)

| Horizon | Aaj ke bucket ({bucket_name.replace('_',' ')}) ke baad BNF | Baseline |
|---|---|---|
| 15 din | {d15a:+.1f}% avg, {d15w}% baar upar | {b15a:+.1f}% / {b15w}% |
| 1 mahina | {m1a:+.1f}% avg, {m1w}% baar upar | {b1a:+.1f}% / {b1w}% |
| 2 mahine | **{m2a:+.1f}% avg, {m2w}% baar upar** | {b2a:+.1f}% / {b2w}% |
{warn}
> 💡 Participant OI (FII/Pro) ka signal poore market ka hai — Bank Nifty par bhi 15 saal test kiya
> (correlation +0.157 @40d). STRONG_UP mein BNF ka 2-mahina record Nifty se bhi tez hai
> (out-of-sample +3.8%/79%). Trade karna ho to **BANKBEES** ETF.
"""
        em = dict(close=f"{last['Close']:,.0f}", chg=f"{chg:+.2f}%", chg_pos=chg >= 0,
                  d15=f"{d15a:+.1f}% / {d15w}%", m1=f"{m1a:+.1f}% / {m1w}%",
                  m2=f"{m2a:+.1f}% / {m2w}%", m2w=m2w, sd=sd)
        return md, em
    except Exception as e:
        print(f"[bnf] skip: {e}")
        return "", {}

def main():
    added = fetch_oi.update_master(lookback_days=7)
    update_prices()
    p = predict()
    p["generated_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    p["new_oi_dates_added"] = added
    (OUT / "prediction_today.json").write_text(json.dumps(p, indent=2))

    # --- simple keys nikalo ---
    es = p["MASTER_entry_signal"]
    key = "STRONG" if "STRONG" in es else "MEDIUM" if "MEDIUM" in es else \
          "WEAK" if "WEAK" in es else "WAIT" if "WAIT" in es else "NO"
    pct = int("".join(ch for ch in p["MASTER_deploy_signal"] if ch.isdigit()))
    S = SIMPLE[key]; D = DEPLOY_SIMPLE[pct]
    lakh = pct * 1000  # ₹1,00,000 example

    # STALE-DATA WATCHDOG: agar OI data 4+ din purana hai to report mein bada warning
    ist_now = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()
    stale_days = (ist_now - dt.date.fromisoformat(str(p["data_date"]))).days
    stale_warn = ""
    if stale_days > 4:
        stale_warn = (f"⚠️ DHYAN DO: Data {stale_days} din PURANA hai "
                      f"(latest {p['data_date']}) — NSE fetch mein dikkat lag rahi hai, "
                      f"is report par bharosa mat karo jab tak fresh na ho!")
        print(f"[watchdog] {stale_warn}")

    hist = OUT / "prediction_history.csv"
    # 🚨 SIGNAL-CHANGE ALERT (Addition v18-D): pichhle din se kya badla?
    alert = ""
    try:
        if hist.exists():
            rows = [r for r in hist.read_text().strip().split("\n")[1:] if r]
            prev_rows = [r for r in rows if not r.startswith(str(p["data_date"]) + ",")]
            if prev_rows:
                pr = prev_rows[-1].split(",")
                prev_bucket, prev_key, prev_b3, prev_t4 = pr[2], pr[4], pr[6], pr[7]
                changes = []
                if prev_bucket != p["bucket"]:
                    changes.append(f"{prev_bucket.replace('_',' ')} -> {p['bucket'].replace('_',' ')}")
                if prev_key != key:
                    changes.append(f"entry {prev_key} -> {key}")
                if ("ACTIVE" in p["bottom_signal_B3"]) != ("ACTIVE" in prev_b3):
                    changes.append("🟢 BOTTOM signal " + ("FIRE hua!" if "ACTIVE" in p["bottom_signal_B3"] else "band hua"))
                if ("ACTIVE" in p["top_warning_T4"]) != ("ACTIVE" in prev_t4):
                    changes.append("🔴 TOP warning " + ("FIRE hua!" if "ACTIVE" in p["top_warning_T4"] else "band hua"))
                if changes:
                    alert = " | ".join(changes)
                    print(f"[alert] SIGNAL BADLA: {alert}")
    except Exception as e:
        print(f"[alert] skip: {e}")
    line = f'{p["data_date"]},{p["score_v2"]},{p["bucket"]},{p["nifty_close"]},{key},{pct}%,{p["bottom_signal_B3"]},{p["top_warning_T4"]}\n'
    if not hist.exists():
        hist.write_text("data_date,score_v2,bucket,nifty_close,entry_signal,deploy_pct,bottom_B3,top_T4\n")
    if p["data_date"] not in hist.read_text():
        with open(hist, "a") as f: f.write(line)

    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(S["kya_karna"]))
    trend = "UPAR ⬆️" if "100%" in p["layer1_base_allocation"] or p["nifty_close"] > p["dma200"] else "NEECHE ⬇️"
    warn_md = f"\n> ## {stale_warn}\n" if stale_warn else ""
    hz_md, hz_email = horizon_section(p["bucket"], fast_pulse())
    # 📒 MASTER SIGNAL REPORT CARD (Addition #10) — fail-safe
    try:
        from signal_tracker import build_scorecard
        card_md, card_email = build_scorecard()
    except Exception as e:
        print(f"[scorecard] skip: {e}")
        card_md, card_email = "", {}
    # 📋 VIRTUAL POSITION TRACKER (v18-F) — system ka khula swing trade
    try:
        from position_tracker import update_position
        pos_md, pos_email = update_position(p)
    except Exception as e:
        print(f"[position] module fail: {e}")
        pos_md, pos_email = "", {}
    # 🏦 BANK NIFTY section (v18-B)
    bnf_md, bnf_email = bnf_section(p["bucket"])
    # 🏆 STOCK SWEEP (v18-E) — Nifty50 ke strongest stocks
    try:
        from stock_sweep import screen_stocks
        stk_md, stk_rows = screen_stocks()
    except Exception as e:
        print(f"[stocks] module fail: {e}")
        stk_md, stk_rows = "", []
    # 💎 GEM SCANNER (v21) — 25-40% mover setup, 15y decoded
    try:
        from gem_scanner import scan_gems
        gem_md, gem_email = scan_gems()
    except Exception as e:
        print(f"[gems] module fail: {e}")
        gem_md, gem_email = "", {}
    # 🧭 SECTOR ROTATION (v20) — bullish-conditional, 15y tested
    try:
        from sector_rotation import sector_section
        sect_md, sect_email = sector_section(float(p["score_v2"]))
    except Exception as e:
        print(f"[sector] module fail: {e}")
        sect_md, sect_email = "", {}
    alert_md = f"\n> # 🚨 SIGNAL BADLA AAJ: {alert}\n" if alert else ""
    md = f"""{warn_md}{alert_md}# 🙋 AAJ KA SIGNAL — Simple Bhasha Mein
### Date: {p['data_date']} (shaam ke NSE data se) | Nifty: {p['nifty_close']}

---

## {S['emoji']} EK LINE MEIN:
> **{S['one_liner']}**

---

## ✅ STEP-BY-STEP — AAJ KARNA KYA HAI:
{steps}

---

## 💰 TOTAL KITNA PAISA MARKET MEIN RAKHNA HAI: **{pct}%**
Matlab: agar tumhare paas kul **₹1,00,000** hai investing ke liye, to abhi sirf
**₹{lakh:,}** market mein ho aur **₹{100000-lakh:,} cash** mein.
Kyun? {D[0]} — isliye {D[1]}.

---

## 📖 MARKET KA HAAL (simple):
| Cheez | Status | Matlab |
|---|---|---|
| Market ka trend | **{trend}** | Nifty apni 200-din ki average price se {"upar hai = healthy" if trend.startswith("UPAR") else "niche hai = kamzor"} |
| Bade khiladi (FII/operators) | **{p['bucket'].replace('_',' ')}** | score {p['score_v2']:+.2f} (+2.5 se upar = zor se kharid rahe; -2.5 se niche = zor se bech rahe) |
| 🟢 Bottom signal | **{p['bottom_signal_B3']}** | {"Market sasta + bade log kharid rahe = bottom banne wala hai (10 mein 8 baar sahi)" if "ACTIVE" in p['bottom_signal_B3'] else "abhi nahi"} |
| 🔴 Top warning | **{p['top_warning_T4']}** | {"Sab log overconfident = top ke paas ho sakte hain, profit bachao" if "ACTIVE" in p['top_warning_T4'] else "abhi nahi"} |

**Is signal ki accuracy:** {S['accuracy']}

---

{hz_md}
{card_md}
{pos_md}
{bnf_md}
{sect_md}
{gem_md}
{stk_md}
---

## 🧒 PAKKE NIYAM (har naye bande ke liye, HAMESHA):
1. **Stop-loss -10%:** jo bhi kharido, kharid-price se 10% girte hi bech do. Bina sawal. (15-saal test: -8% se -10% behtar nikla — bazaar ke chhote jhatke trade ko bekar mein nahi todte, aur bade nuksan se phir bhi bachata hai.)
2. **Kabhi ek saath pura paisa nahi** — hamesha 2-3 kisht mein.
3. **Udhaar/EMI/zaroorat ka paisa KABHI nahi** — sirf wo paisa jo 6 mahine na chahiye.
4. Ye system 10 mein se 7-8 baar sahi hai — **2-3 baar galat bhi hoga.** Isliye upar ke niyam hi tumhara asli bachav hain.
5. Kya kharidna hai confusion ho to: **NIFTYBEES** (Nifty 50 ETF) — isi index par ye pura system bana hai.

*Ye financial advice nahi hai — 15 saal ke data par bana educational system hai. | Generated: {p['generated_utc']} UTC*
"""
    # --- INDEX SWEEP SCANNER sections: daily + weekly (konsa index strong hai) ---
    sweep_md, sweep_setups, weekly_setups, sweep_extras = sweep_scan_section()
    if sweep_md:
        md += "\n---\n\n" + sweep_md + "\n"
    (OUT / "PREDICTION.md").write_text(md)

    # --- Telegram alert (optional — repo secrets set karo to phone par aayega) ---
    import os, requests as rq
    tok = os.environ.get("TELEGRAM_BOT_TOKEN"); chat = os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        msg = ((f"🚨 SIGNAL BADLA: {alert}\n\n" if alert else "") +
               f"{S['emoji']} NIFTY OI SIGNAL — {p['data_date']}\n\n"
               f"{S['one_liner']}\n\n"
               f"KITNA INVESTED: {pct}% (₹1L mein ₹{lakh:,})\n"
               f"Bottom signal: {p['bottom_signal_B3']} | Top warning: {p['top_warning_T4']}\n"
               f"Nifty: {p['nifty_close']} | Score: {p['score_v2']:+.2f}")
        if sweep_setups:
            names = ", ".join(f"{s['Index']} ({s['Grade']})" for s in sweep_setups[:3])
            msg += f"\n\n🧲 Daily sweep setups: {names}"
        if gem_email and gem_email.get("n"):
            gnames = ", ".join(c[0] for c in gem_email["cands"])
            msg += f"\n\n💎 GEM SETUP AAJ: {gnames} (stop -12%, target +25%)"
        if weekly_setups:
            wnames = ", ".join(f"{s['Index']} ({s['Grade']})" for s in weekly_setups[:3])
            msg += f"\n📅 WEEKLY sweep (strong!): {wnames}"
        try:
            rq.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                    json={"chat_id": chat, "text": msg}, timeout=15)
            print("[telegram] sent")
        except Exception as e:
            print(f"[telegram] fail: {e}")

    # --- GMAIL REPORT (professional HTML — repo secrets: GMAIL_USER + GMAIL_APP_PASSWORD) ---
    try:
        from emailer import send_email
        inline = []
        for cap, path in sweep_extras.get("chart_files", [])[:3]:
            cp = Path(path)
            if not cp.is_absolute():
                cp = OUT / "charts" / cp.name
            if cp.exists():
                inline.append((cap, str(cp)))
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        repo_url = (f"https://github.com/{repo}/blob/main/output/PREDICTION.md" if repo else "")
        ctx = dict(p=p, key=key, S=S, D=D, pct=pct, lakh=lakh, trend=trend,
                   sweep_setups=sweep_setups, weekly_setups=weekly_setups,
                   drows=sweep_extras.get("drows", []), wrows=sweep_extras.get("wrows", []),
                   inline_charts=inline, repo_url=repo_url, warn=stale_warn, horizon=hz_email,
                   scorecard=card_email, alert=alert, position=pos_email,
                   bnf=bnf_email, stocks=stk_rows, sector=sect_email, gems=gem_email)
        send_email(ctx, OUT)
    except Exception as e:
        print(f"[email] module fail: {e}")

    print(json.dumps(p, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
