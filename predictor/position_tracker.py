#!/usr/bin/env python3
"""VIRTUAL POSITION TRACKER (Addition v18-F)
System ka official swing trade (B3 STRONG_BUY) ka poora lifecycle manage karta hai:
entry -> roz ka P&L -> stop-loss (-10%, 15y tested) -> exit signal (v2 <= -2.5).
Scorecard ki tarah imandar — jhooth nahi chhupa sakta (sab position_history.csv mein).
Fail-safe: koi error aaye to ("", {}) return karo, baki report kharab na ho.
"""
import json
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
STATE = OUT / "position_state.json"
HIST = OUT / "position_history.csv"

STOP_PCT = 0.10          # -10% hard stop (EXIT battery v19: -8% se behtar dono periods — IS +2.31%/71% vs +2.09%/67%, OOS +0.88% vs +0.56%; kam whipsaw)
EXIT_SCORE = -2.5        # v2 score is ke neeche => exit (B3 swing exit rule)


def _load_state():
    try:
        if STATE.exists():
            return json.loads(STATE.read_text())
    except Exception:
        pass
    return {}


def _save_state(st):
    try:
        STATE.write_text(json.dumps(st, indent=2))
    except Exception as e:
        print(f"[position] state save fail: {e}")


def _log_close(st, exit_price, reason, date):
    try:
        if not HIST.exists():
            HIST.write_text("entry_date,entry_price,exit_date,exit_price,pnl_pct,reason\n")
        pnl = (exit_price / st["entry_price"] - 1) * 100
        with open(HIST, "a") as f:
            f.write(f'{st["entry_date"]},{st["entry_price"]},{date},{exit_price},{pnl:+.2f},{reason}\n')
    except Exception as e:
        print(f"[position] history log fail: {e}")


def update_position(p):
    """p = prediction dict (data_date, nifty_close, score_v2, bottom_signal_B3).
    Returns (md_section, email_ctx) — dono fail-safe."""
    try:
        close = float(p["nifty_close"])
        score = float(p["score_v2"])
        date = str(p["data_date"])
        b3_on = "ACTIVE" in str(p.get("bottom_signal_B3", ""))
        st = _load_state()

        closed_today = None
        if st.get("open"):
            # same-date re-run par double update mat karo — bas display refresh
            stop = st["entry_price"] * (1 - STOP_PCT)
            if close <= stop:
                closed_today = ("STOP-LOSS HIT (-10%)", close)
            elif score <= EXIT_SCORE:
                closed_today = (f"EXIT SIGNAL (score {score:+.1f} <= -2.5)", close)
            if closed_today:
                _log_close(st, close, closed_today[0], date)
                st = {"open": False, "last_exit": {
                    "entry_date": st["entry_date"], "entry_price": st["entry_price"],
                    "exit_date": date, "exit_price": close,
                    "pnl": (close / st["entry_price"] - 1) * 100,
                    "reason": closed_today[0]}}
                _save_state(st)
        if not st.get("open") and b3_on and not closed_today:
            # naya official swing trade kholo (B3 STRONG_BUY fire)
            if st.get("entry_date") != date:   # idempotent re-run guard
                st = {"open": True, "entry_date": date, "entry_price": close,
                      "stop": round(close * (1 - STOP_PCT), 2)}
                _save_state(st)

        # ---------- render ----------
        em = {}
        if st.get("open"):
            entry = st["entry_price"]
            pnl = (close / entry - 1) * 100
            stop = st.get("stop", round(entry * (1 - STOP_PCT), 2))
            dist = (close / stop - 1) * 100
            days = max(0, (dt.date.fromisoformat(date) - dt.date.fromisoformat(st["entry_date"])).days)
            exit_line = "score abhi " + f"{score:+.1f}" + " (exit jab <= -2.5) — HOLD"
            md = f"""## 📋 SYSTEM KA KHULA SWING TRADE (virtual — NIFTYBEES/Nifty)

| Cheez | Status |
|---|---|
| Entry | **{entry:,.0f}** ({st['entry_date']}, B3 STRONG_BUY par) |
| Abhi | **{close:,.0f}** → P&L **{pnl:+.2f}%** {'🟢' if pnl >= 0 else '🔴'} |
| Stop-loss (-10%) | **{stop:,.0f}** (abhi stop se {dist:+.1f}% upar) |
| Exit signal | {exit_line} |
| Hold duration | {days} din (target hold: 1-2 mahine) |

> 🎯 **Matlab:** trade chaalu hai — kuch mat karo. Sirf 2 cheez par exit: (1) Nifty {stop:,.0f} ke neeche band ho, ya (2) yahan exit signal aa jaye. Beech ka shor ignore.
"""
            em = dict(status="OPEN", entry=f"{entry:,.0f}", entry_date=st["entry_date"],
                      now=f"{close:,.0f}", pnl=f"{pnl:+.2f}%", pnl_pos=pnl >= 0,
                      stop=f"{stop:,.0f}", dist=f"{dist:+.1f}%", days=days)
        elif st.get("last_exit"):
            le = st["last_exit"]
            recent = (dt.date.fromisoformat(date) - dt.date.fromisoformat(le["exit_date"])).days <= 7
            if recent:
                md = f"""## 📋 SWING TRADE BAND HUA (virtual)

Pichla trade: entry {le['entry_price']:,.0f} ({le['entry_date']}) → exit {le['exit_price']:,.0f} ({le['exit_date']})
= **{le['pnl']:+.2f}%** | Wajah: {le['reason']}

> Abhi koi khula trade nahi. Agla STRONG_BUY (B3) aane par naya trade khulega — email khud bata dega.
"""
                em = dict(status="CLOSED", entry=f"{le['entry_price']:,.0f}", entry_date=le["entry_date"],
                          now=f"{le['exit_price']:,.0f}", pnl=f"{le['pnl']:+.2f}%",
                          pnl_pos=le["pnl"] >= 0, reason=le["reason"])
            else:
                md = ""
        else:
            md = ""
        return md, em
    except Exception as e:
        print(f"[position] skip: {e}")
        return "", {}
