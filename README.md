# 📈 Nifty OI Predictor — Participant-wise OI Swing System

NSE participant-wise Open Interest data se **roz automatic swing-trading prediction**
(40-60 din horizon). Amit Dhamija ke system ka decoded + improved (v2) version —
**15 saal (2012-2026, 3,634 din) par backtested.**

## ✅ Backtest-verified edge
| Signal | 60-din forward | Observations |
|---|---|---|
| STRONG_UP | **78% up-rate, +4.1% avg** | 974 |
| STRONG_DOWN | 53% up-rate, +0.6% avg | 787 |

IC@40d = +0.21, **13/15 saal positive**. (2017-type low-vol melt-up = weak regime, dhyan rahe.)

## 🏗️ 3-Layer system
1. **L1 Base allocation** — Nifty vs 200DMA: upar → 100% invested, niche → 30%
2. **L2 Entry sizing** — v2 OI score: STRONG_UP → full size, MILD/NEUTRAL → half, STRONG_DOWN → koi naya entry nahi
3. **L3 Outlook** — 40-60 din ka expectation table

## 🤖 Kaise chalta hai (sab FREE)
GitHub Actions roz **19:45 IST** (+ retry 21:15):
NSE se participant OI CSV fetch (3 fallback routes) → master CSV append →
v2 score → `output/PREDICTION.md` + `prediction_today.json` + history commit.

## 🚀 Setup (one-time, 2 minute)
1. Is folder ko GitHub par naye repo mein push karo
2. Repo Settings → Actions → General → Workflow permissions → **Read and write** ✅
3. Actions tab → "Daily OI Prediction" → **Run workflow** (pehla manual test)
4. Bas! Roz shaam `output/PREDICTION.md` mein fresh prediction

## 📁 Structure
- `predictor/fetch_oi.py` — NSE data fetcher (direct → jina.ai → urltomarkdown fallback)
- `predictor/model.py` — v2 score + 3-layer logic
- `predictor/run.py` — daily runner
- `data/participant_oi_master.csv` — 15 saal ka seed data (2012 →)
- `output/PREDICTION.md` — **aaj ka prediction (yahan dekho)**

*Educational purpose only. Not financial advice.*
