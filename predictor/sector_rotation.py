#!/usr/bin/env python3
"""SECTOR ROTATION (Addition v20) — 130-stock / 16-sector universe, 15y tested.
TESTED RULE (IS<2020 / OOS>=2020, fwd vs all-stock baseline, T+1 entry):
  ACTIVE sirf jab v2 >= +1.0 (MILD_UP / STRONG_UP):
    TOP-2 sectors (126d momentum, equal-weight member basket):
      @20d +0.21/+0.47pp · @40d +0.76/+1.01pp · @60d +1.41/+0.79pp  (6/6 cells positive)
REJECTED (do not re-add):
  - unconditional sector rotation (OOS -0.3 to -1.1pp — 2020 ke baad mar gaya)
  - within-sector stock filters: RS+EMA50 / top-3 RS (IS-OOS inconsistent)
  - top-1 sector only (too concentrated, OOS negative)
Honest note: universe = AAJ ke constituents (survivorship bias in level terms;
relative sector-vs-sector compare se kaafi had tak cancel hota hai).
Fail-safe: error -> ("", {}).
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "sector_universe_close.csv"
SECTORS = ROOT / "data" / "stock_sectors.csv"

ETF = {"Bank": "BANKBEES", "IT": "ITBEES", "Pharma": "PHARMABEES", "Auto": "AUTOBEES",
       "FMCG": "FMCGBEES*", "Metal": "METALBEES*"}  # * = check availability


def _update_prices():
    try:
        df = pd.read_csv(PRICES, parse_dates=["Date"]).set_index("Date")
    except Exception as e:
        print(f"[sector] data load fail: {e}")
        return None
    try:
        import yfinance as yf
        new = yf.download([c + ".NS" for c in df.columns], period="10d", interval="1d",
                          auto_adjust=True, progress=False, threads=True)["Close"]
        new.columns = [c.replace(".NS", "") for c in new.columns]
        new = new.reindex(columns=df.columns)
        new.index = pd.to_datetime(new.index).tz_localize(None).normalize()
        add = new[~new.index.isin(df.index)].dropna(how="all")
        if len(add):
            df = pd.concat([df, add]).sort_index()
            df.round(2).to_csv(PRICES)
            print(f"[sector] +{len(add)} naye din (latest {df.index[-1].date()})")
    except Exception as e:
        print(f"[sector] yfinance update fail ({e}) — purana data use")
    return df


def sector_section(score_v2):
    """Returns (md, em). em = dict(active, ranks=[(sector, mom%, badge)], top=[...], stocks=[...])"""
    try:
        px = _update_prices()
        if px is None or len(px) < 200:
            return "", {}
        px = px.ffill()
        sec = pd.read_csv(SECTORS, index_col=0)["sector"]
        sec = sec[sec.index.isin(px.columns)]
        ret126 = px.pct_change(126, fill_method=None)
        last_r = ret126.iloc[-1]

        rows = []
        for s in sorted(sec.unique()):
            mem = sec[sec == s].index
            r = last_r[mem].dropna()
            if len(r) >= 3:
                rows.append((s, r.mean() * 100))
        rows.sort(key=lambda x: -x[1])
        if len(rows) < 8:
            return "", {}
        top2 = [rows[0][0], rows[1][0]]
        bot2 = [rows[-1][0], rows[-2][0]]
        active = score_v2 >= 1.0
        # SAFETY RAIL (15y test: neutral — sirf rare all-negative regime guard, 6/153 cases):
        # agar top-2 ka khud ka momentum bhi negative hai to tilt mat do ("least bad" trap)
        neg_trap = all(m <= 0 for _, m in rows[:2])
        if neg_trap:
            active = False

        # top-2 ke member stocks, RS ke order mein (display — filtering ka edge test mein NAHI mila,
        # isliye recommendation = poora basket / barabar baanto)
        stocks = []
        for s in top2:
            mem = last_r[sec[sec == s].index].dropna().sort_values(ascending=False)
            stocks.append((s, [(m, f"{mem[m]*100:+.0f}%") for m in mem.index]))

        rank_md = "\n".join(
            f"| {i+1} | {'🟢' if s in top2 else ('🔴' if s in bot2 else '·')} **{s}** | {m:+.1f}% |"
            for i, (s, m) in enumerate(rows))
        if active:
            head = (f"**✅ ACTIVE** — OI signal bullish hai (score {score_v2:+.1f} ≥ +1.0), "
                    f"to sector tilt ka tested edge ABHI chalu hai.")
            advice = (f"**Kya karna:** Agar stocks lene hain to in 2 sectors ke stocks mein lagao — "
                      f"**{top2[0]} + {top2[1]}**. 15-saal test: in top-2 sectors ka basket, bullish signal ke "
                      f"waqt, baaki market se **+0.8 se +1.0pp (40 din) / +0.8 se +1.4pp (60 din)** aage raha "
                      f"(out-of-sample bhi). ⚠️ Lekin: sector ke 1-2 stocks chunne ka edge test mein NAHI mila — "
                      f"**sector ke 3-4 bade stocks mein barabar baanto** (ya ETF jahan available: "
                      + ", ".join(f"{s}→{ETF[s]}" for s in top2 if s in ETF) + ").")
        elif neg_trap and score_v2 >= 1.0:
            head = ("**⏸️ STANDBY (safety)** — OI signal to bullish hai, par SAARE sectors ka 6-mahina "
                    "momentum negative hai — 'sabse kam bura' sector chunna trap hai. Intezaar karo.")
            advice = "**Kya karna:** Intezaar — jab sectors mein asli taqat lautegi, section khud ACTIVE ho jayega."
        else:
            head = (f"**⏸️ STANDBY** — OI signal abhi bullish nahi (score {score_v2:+.1f} < +1.0). "
                    f"15-saal test ne saaf dikhaya: sector tilt **sirf bullish signal ke saath** kaam karta hai "
                    f"(bina signal: out-of-sample NEGATIVE tha). Isliye abhi sirf ranking dekho, lagao mat.")
            advice = "**Kya karna:** Intezaar. Jab upar wala signal MILD_UP/STRONG_UP ho, tab ye section ACTIVE ho jayega."

        stock_lines = "\n".join(
            f"- **{s}:** " + ", ".join(f"{m} ({r})" for m, r in lst[:6])
            for s, lst in stocks)

        md = f"""## 🧭 SECTOR ROTATION — SABSE MAJBOOT SECTOR (15-saal tested)

{head}

| Rank | Sector | 6-mahina momentum |
|---|---|---|
{rank_md}

{advice}

**Top-2 sectors ke stocks (RS order, sirf jankari ke liye):**
{stock_lines}

> 🔴 = sabse kamzor 2 sectors — yahan naya paisa mat lagao.
> 📏 Rule yaad rakho: KAB/KITNA upar ka MASTER SIGNAL batata hai — ye section sirf **KAHAN** (kaunsa sector) batata hai. Stop-loss -10% yahan bhi.
"""
        em = dict(active=active,
                  ranks=[(s, f"{m:+.1f}%", "top" if s in top2 else ("bot" if s in bot2 else "")) for s, m in rows],
                  top=top2,
                  stocks=[(s, ", ".join(f"{m} {r}" for m, r in lst[:4])) for s, lst in stocks])
        return md, em
    except Exception as e:
        print(f"[sector] skip: {e}")
        return "", {}
