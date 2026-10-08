#!/usr/bin/env python3
"""📒 MASTER SIGNAL REPORT CARD — system apni predictions ka hisaab khud deta hai.

Roz ka bucket-signal (v2 score se) deterministic hai — isliye ledger ko har run par
model se dobara banate hain (koi alag history file ki zaroorat nahi, koi lookahead nahi:
signal din T ke OI se, result T ke close se aage ka).

Grading (HORIZON_STATS ke hisaab se — wahi jo report mein promise karte hain):
- STRONG_UP / MILD_UP / NEUTRAL / MILD_DOWN: expectation = 20d/40d mein UPAR → ✅ agar ret > 0
- STRONG_DOWN: expectation = "paisa mat lagao, aage kamzori" → ✅ agar 20d ret < +1.0%
  (baseline ~+1.0% hai; usse neeche raha to warning sahi thi)

Fail-safe: koi bhi error → empty section, report kharab nahi hoti.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

BULLISH = {"STRONG_UP", "MILD_UP", "NEUTRAL", "MILD_DOWN"}


def _bucket(s):
    if s >= 2.5:
        return "STRONG_UP"
    if s >= 1.0:
        return "MILD_UP"
    if s <= -2.5:
        return "STRONG_DOWN"
    if s <= -1.0:
        return "MILD_DOWN"
    return "NEUTRAL"


def _hit(bucket, r20, r40):
    """(hit20, hit40) booleans."""
    if bucket == "STRONG_DOWN":
        return (r20 < 1.0), (r40 < 2.0)   # baseline 20d ~+1.0%, 40d ~+2.0%
    return (r20 > 0), (r40 > 0)


def build_scorecard(months=12):
    """Return (markdown_section, email_ctx_dict). Empty strings/dict on failure."""
    try:
        from model import load_wide, v2_scores
        w = load_wide()
        sc = v2_scores(w)
        score = sc["slow_v2"].dropna()
        px = pd.read_csv(ROOT / "data/nifty_close.csv", parse_dates=[0], index_col=0).iloc[:, 0]
        idx = score.index.intersection(px.index).sort_values()
        score, px = score.loc[idx], px.loc[idx].astype(float)
        bk = score.apply(_bucket)
        r20 = (px.shift(-20) / px - 1) * 100
        r40 = (px.shift(-40) / px - 1) * 100

        # --- matured signals, pichhle `months` mahine ---
        matured = r40.notna()
        cutoff = idx.max() - pd.DateOffset(months=months)
        recent = matured & (pd.Series(idx, idx) >= cutoff)
        if recent.sum() < 30:                      # bahut kam sample → 24 mahine le lo
            cutoff = idx.max() - pd.DateOffset(months=24)
            recent = matured & (pd.Series(idx, idx) >= cutoff)

        rows = []
        for d in idx[recent]:
            h20, h40 = _hit(bk[d], r20[d], r40[d])
            rows.append((d, bk[d], r20[d], r40[d], h20, h40))
        df = pd.DataFrame(rows, columns=["date", "bucket", "r20", "r40", "h20", "h40"])
        n = len(df)
        hit20 = df.h20.mean() * 100
        hit40 = df.h40.mean() * 100

        per = df.groupby("bucket").agg(n=("h20", "size"), hit20=("h20", "mean"),
                                       hit40=("h40", "mean"), avg20=("r20", "mean"),
                                       avg40=("r40", "mean"))
        order = ["STRONG_UP", "MILD_UP", "NEUTRAL", "MILD_DOWN", "STRONG_DOWN"]
        per = per.reindex([b for b in order if b in per.index])

        # --- abhi ke OPEN (unmatured) signals — running result ---
        open_rows = []
        last_px = px.iloc[-1]
        for i_pos in range(max(0, len(idx) - 40), len(idx)):
            d = idx[i_pos]
            if pd.notna(r40.iloc[i_pos]):
                continue
            days = len(idx) - 1 - i_pos
            if days == 0:
                continue
            run = (last_px / px.iloc[i_pos] - 1) * 100
            open_rows.append((d, bk.iloc[i_pos], days, run))
        open_rows = open_rows[-5:]

        # ---------- markdown ----------
        tbl = "| Bucket | Signals | 20-din sahi | 40-din sahi | Avg 20d | Avg 40d |\n|---|---|---|---|---|---|\n"
        for b, r in per.iterrows():
            tbl += (f"| {b} | {int(r['n'])} | {r['hit20']*100:.0f}% | {r['hit40']*100:.0f}% "
                    f"| {r['avg20']:+.1f}% | {r['avg40']:+.1f}% |\n")

        recent_lines = ""
        for _, r in df.tail(6).iloc[::-1].iterrows():
            recent_lines += (f"| {r['date'].date()} | {r['bucket']} | {r['r20']:+.1f}% "
                             f"{'✅' if r['h20'] else '❌'} | {r['r40']:+.1f}% "
                             f"{'✅' if r['h40'] else '❌'} |\n")

        open_lines = ""
        for d, b, days, run in reversed(open_rows):
            open_lines += f"| {d.date()} | {b} | {days} din | {run:+.1f}% ⏳ |\n"

        period_lbl = f"pichhle {months} mahine" if n >= 30 else "pichhle 24 mahine"
        md = f"""## 📒 SYSTEM KA APNA REPORT CARD ({period_lbl} ke {n} daily signals — khud ka hisaab)

**20-din accuracy: {hit20:.0f}%  |  40-din accuracy: {hit40:.0f}%** (✅ = jo promise kiya wahi hua: bullish/neutral bucket → market upar; STRONG_DOWN → market baseline se kamzor)

{tbl}
**Aakhri 6 pakke (matured) signals:**

| Signal din | Bucket | 20-din result | 40-din result |
|---|---|---|---|
{recent_lines}
**Abhi chal rahe (open) signals:**

| Signal din | Bucket | Beete din | Ab tak |
|---|---|---|---|
{open_lines}
> 🪞 **Ye section khud-ba-khud roz update hota hai — system apne purane signals se bhaag nahi sakta.** Accuracy girne lage to turant dikh jayega.
"""
        em = dict(n=n, hit20=round(hit20), hit40=round(hit40),
                  last=[(str(r["date"].date()), r["bucket"],
                         f"{r['r40']:+.1f}%", bool(r["h40"])) for _, r in df.tail(3).iloc[::-1].iterrows()])
        return md, em
    except Exception as e:
        print(f"[scorecard] fail-safe: {e}")
        return "", {}


if __name__ == "__main__":
    md, em = build_scorecard()
    print(md[:2000])
    print(em)
