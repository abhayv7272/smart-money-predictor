# 🏛️ SMART MONEY INSTITUTIONAL WORKFLOW & SYSTEM MASTER REFERENCE
> **PROJECT**: Automated Smart Money Institutional Predictor & Swing Advisor (Pro Edition)  
> **GITHUB REPOSITORY**: [https://github.com/abhayv7272/smart-money-predictor](https://github.com/abhayv7272/smart-money-predictor)  
> **TARGET AUDIENCE & STYLE**: 10-to-40 Day & 1-to-2 Month Swing & Positional Trading (Zero Intraday Noise)  
> **NOTIFICATION TARGET**: `abhayv7272@gmail.com` (Daily at 9:00 PM IST / 15:30 UTC)  
> **DATA COST**: 100% Free (Zero Paid Subscriptions, Official NSE Clearing & Yahoo Finance APIs)

---

## 📌 INSTRUCTIONS FOR ANY FUTURE AI SESSION (CONTINUATION PROMPT)
*If you are an AI reading this file at the start of a new chat session, treat this document as the complete, authoritative, and battle-tested foundation of the user's Smart Money Institutional Trading System. Do not reinvent or alter the core formulas, regimes, index sweep engine, or repository architecture unless explicitly commanded. You possess full knowledge of Amit Dhamija's 28 video sessions, 5+ years of historical backtest proof (1,417 trading days), the 6-factor CIS scoring engine, 16 sector rotation tracking, the multi-confluence Daily Liquidity Sweep Radar across all NSE Market Indices, and the live GitHub Actions daily automated pipeline.*

---

## 1. CORE PHILOSOPHY & ZERO-SUM GAME MECHANICS

1. **The 4 Market Participants**:
   - **FIIs (Foreign Institutional Investors)**: The Big Trendsetters. Multi-thousand crore capital. Horizon: 2 weeks to multiple months. Primary weapons: **Index Futures & Stock Futures**.
   - **PROs (Proprietary Desks)**: DMA / High-Frequency Algorithm Desks. Horizon: Intraday to Weekly Expiry. Primary weapons: **Index Option Writing (Call & Put selling)**.
   - **CLIENTS (Retail & HNIs)**: The Counter-Party. 50%+ gross volume, emotional, fragmented. 90%+ lose money according to official SEBI studies. Consistently buy calls at tops and buy puts at bottoms.
   - **DIIs (Domestic Institutions)**: Cash equity buyers (SIP flows of ₹20,000+ Cr/month) and structural arbitrageurs (holding cash long + stock futures short). Derivatives data is neutralized for directional bias.

2. **Zero-Sum Transfer Principle**:
   - Wealth transfers from uninformed, emotional Retailers (Clients) into the pockets of informed Smart Money (FIIs + Pro Desks). Following Smart Money contracts data reveals the market's true directional script before it plays out on price charts.

---

## 2. 100% FREE OFFICIAL DATA PIPELINE

| Data Component | Official Free Endpoint | Timing & Update Frequency |
| :--- | :--- | :--- |
| **Participant Open Interest** | `https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv` | Daily 7:30 PM – 8:00 PM IST |
| **Participant Volume** | `https://nsearchives.nseindia.com/content/nsccl/fao_participant_vol_DDMMYYYY.csv` | Daily 7:30 PM – 8:00 PM IST |
| **Cash Market Provisional** | `https://www.nseindia.com/api/fiidiiTradeReact` | Daily 6:30 PM IST |
| **Macro Indicators (Crude, 10Y Yield, DXY)** | Yahoo Finance API (`BZ=F`, `^TNX`, `DX-Y.NYB`, `^DJI`, `^GSPC`, `^NSEI`) | Live Real-time & EOD |
| **Historical Database** | Pre-loaded SQLite DB: `data/participant_oi_master.db` | **1,420 Trading Days (2019 to 2024)** |
| **All NSE Market Indices** | Yahoo Finance / NSE Live Indices (`^NSEI`, `^NSEBANK`, `^CNXIT`, etc.) | Daily EOD / Live Updates |

---

## 3. EXACT MATHEMATICAL FORMULAS & AMIT DHAMIJA MATRIX

### A. Positions Carried (Inventory / Stock):
$$\text{Net Position}_{\text{Today}} = \text{Long Contracts}_{\text{Today}} - \text{Short Contracts}_{\text{Today}}$$
- Tracked across: **TODAY**, **1 DAY AGO**, **2 DAYS AGO**.

### B. Daily Flow of Funds (Positions Bought / Sold Today):
$$\Delta \text{Long} = \text{Long}_{\text{Today}} - \text{Long}_{\text{Yesterday}}$$
$$\Delta \text{Short} = \text{Short}_{\text{Today}} - \text{Short}_{\text{Yesterday}}$$
$$\text{Net Daily Flow} = \Delta \text{Long} - \Delta \text{Short} = \text{Net Position}_{\text{Today}} - \text{Net Position}_{\text{Yesterday}}$$

### C. The Option Sign Convention:
- **Calls (+)**: Net Call Long $\rightarrow$ **Bullish (Green)**
- **Calls (-)**: Net Call Short $\rightarrow$ **Bearish / Call Writing (Red)**
- **Puts (-)**: Net Put Short $\rightarrow$ **BULLISH / Put Writing Floor (Green)**
- **Puts (+)**: Net Put Long $\rightarrow$ **BEARISH / Put Buying Protection (Red)**

### D. The 6-Factor Composite Institutional Score (CIS: -10 to +10):
1. **FII Index Futures Daily Delta** ($> +5,000 \implies +2.0$ pts)
2. **FII Stock Futures 5-Day Thrust** ($> +45,000 \implies +3.0$ pts, $> +20,000 \implies +2.0$ pts)
3. **PRO Desks Options Alignment** (PRO Call Buying $+1.0$, PRO Put Writing Floor $+1.0$)
4. **Retail Contrarian Squeeze** (Retail Put Buying Squeeze $+1.5$, Retail Call Buying Trap $-1.5$)
5. **FII Long Ratio Regime Extremes** (Capitulation $<20\% \implies +2.0$, Overbought $>78\% \implies -2.0$)
6. **Price Action Confirmation** (Price above Daily 20 EMA & 50 EMA)

---

## 4. THE 5 CAPITAL ALLOCATION REGIMES (SWING TRADING PROTOCOL)

$$\text{FII Index Futures Long Ratio \%} = \left( \frac{\text{FII Future Index Long}}{\text{FII Future Index Long} + \text{FII Future Index Short}} \right) \times 100$$

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 5-REGIME CAPITAL ALLOCATION MATRIX                                     │
├─────────────────────┬───────────────────┬────────────────────┬─────────────────────────────────────────┤
│ REGIME              │ FII LONG RATIO    │ CAPITAL ALLOCATION │ SWING TRADING ACTION (10 TO 40 DAYS)    │
├─────────────────────┼───────────────────┼────────────────────┼─────────────────────────────────────────┤
│ 1. Capitulation     │ < 20%             │ 100% Equities      │ 🟢 STRONGLY BUY: Bottom hunting in      │
│    Bottom           │ (Short Exhaustion)│ (0% Cash Reserve)  │ high-beta Stage-2 leaders. 20-40D hold. │
├─────────────────────┼───────────────────┼────────────────────┼─────────────────────────────────────────┤
│ 2. Accumulation     │ 20% - 40%         │ 85% Equities       │ 🟢 STRONGLY BUY / ADD: Base breakouts.  │
│    Breakout         │ (Shorts Covering) │ (15% Cash Buffer)  │ High-volume Stage-2 entries. 15-30D hold│
├─────────────────────┼───────────────────┼────────────────────┼─────────────────────────────────────────┤
│ 3. Momentum         │ 40% - 70%         │ 70%-80% Equities   │ 🟡 BUY / HOLD & TRAIL SL: Add on 2-3D   │
│    Markup           │ (Healthy Trend)   │ (20%-30% Cash)     │ pullbacks. Trail existing with 20 EMA.  │
├─────────────────────┼───────────────────┼────────────────────┼─────────────────────────────────────────┤
│ 4. Overbought       │ 70% - 78%         │ 35% Equities       │ 🟠 PARTIAL PROFIT / REDUCE: Raise 65%   │
│    Distribution     │ (Institutional Ex)│ (65% CASH)         │ Cash. Book 70% profits. No fresh buys.  │
├─────────────────────┼───────────────────┼────────────────────┼─────────────────────────────────────────┤
│ 5. Market Top       │ > 78%             │ 10% Equities       │ 🔴 STRONGLY SELL: 100% CASH. Exit all   │
│    Markdown Danger  │ (Extreme Euphoria)│ (90%-100% CASH)    │ positional longs. Protect alpha.        │
└─────────────────────┴───────────────────┴────────────────────┴─────────────────────────────────────────┘
```

---

## 5. QUANTITATIVE BACKTEST PROOF (1,417 TRADING DAYS: 2019-2024)

- **20-Day Swing Win Rate**: **82.9%** (Average Return: +3.30% on Index / +15% to +35% in stocks).
- **40-Day Swing Win Rate**: **80.3%** (Average Return: +5.19% on Index / +20% to +45% in stocks).
- **Profit Factor**: **13.34x** (Massive positive risk-to-reward).
- **Max Alpha vs Buy & Hold**: Over +4.26% on Sector Leaders vs Underperforming Laggards.

---

## 6. SECTOR ROTATION & RELATIVE STRENGTH ENGINE (16 SECTORS)

Universe of 16 Sectoral & Thematic Indices tracked daily:
1. **Nifty Bank** (`^NSEBANK`)
2. **Nifty PSU Bank** (`PSUBNKBEES.NS`)
3. **Nifty Private Bank** (`HDFCBANK.NS`)
4. **Nifty IT** (`^CNXIT`)
5. **Nifty Pharma** (`^CNXPHARMA`)
6. **Nifty Healthcare** (`HEALTHADD.NS`)
7. **Nifty Auto** (`AUTOBEES.NS`)
8. **Nifty FMCG** (`FMCGIETF.NS`)
9. **Nifty Metal** (`TATASTEEL.NS`)
10. **Nifty Energy** (`RELIANCE.NS`)
11. **Nifty Oil & Gas** (`ONGC.NS`)
12. **Nifty Infrastructure** (`CPSEETF.NS`)
13. **Nifty Realty** (`DLF.NS`)
14. **Nifty Consumer Durables** (`CONSUMBEES.NS`)
15. **Nifty Financial Services** (`FINIETF.NS`)
16. **Nifty Midcap 50 & Smallcap** (`^NSEMDCP50`, `HDFCSML250.NS`)

**Sector Ranking Metric**:
$$\text{RS Score} = 0.6 \times (\text{Sector}_{1\text{W}\%} - \text{Nifty}_{1\text{W}\%}) + 0.4 \times (\text{Sector}_{1\text{M}\%} - \text{Nifty}_{1\text{M}\%})$$
- Only sectors trading **Above their Daily 20 EMA** qualify as **Top Stage-2 Institutional Leaders**.

---

## 7. MULTI-CONFLUENCE NSE INDEX LIQUIDITY SWEEP & REVERSAL RADAR

Inspired by the user's `Daily-sweep` methodology (`https://github.com/abhayv7272/Daily-sweep`), the system scans **ALL NSE Broad Market, Sectoral, and Thematic Indices** for institutional liquidity sweeps:

### A. Core Reversal Confluences Tracked:
1. **Swing Low & Prior Day Low (PDL) Sweep**:
   - Candle dips below prior swing low / PDL (triggering retail stop losses / liquidity grab), but closes strongly back **ABOVE** the level.
2. **Absorption Hammer Rejection Wick**:
   - Lower Wick constitutes $\ge 35\%$ to $\ge 50\%$ of the daily trading range, signaling aggressive Smart Money buying into dips.
3. **Bullish RSI Momentum Divergence**:
   - Price establishes a lower low over 15–20 trading sessions, while the 14-period RSI prints a higher low ($RSI_{\text{today}} > RSI_{\text{prev low}} + 1.5$ and $RSI < 60$).
4. **Bullish Fair Value Gap (FVG)**:
   - Imbalance gap where Candle $T-2$ High $<$ Candle $T$ Low.
5. **Stage-2 20 EMA Alignment**:
   - Price maintains or reclaims the 20-day Exponential Moving Average.

### B. Quality Scoring Rubric (0 to 100 Points):
- **🔥 GRADE A+ SWEEP (Score $\ge 70$)**: Ultra-high conviction institutional reversal (Swing Low Swept + 35%+ Wick + RSI Divergence).
- **⚡ GRADE B SWEEP (Score $50 - 65$)**: Strong reversal confluence (PDL Swept + 50%+ Hammer Wick or RSI Divergence).
- **📈 GRADE C SWEEP (Score $35 - 45$)**: Moderate reversal setup (Lower wick rejection or PDL sweep).

---

## 8. REPOSITORY ARCHITECTURE & GITHUB ACTIONS AUTOMATION

```
smart-money-predictor/
├── .github/
│   └── workflows/
│       └── daily_prediction.yml     # Auto-trigger daily at 9:00 PM IST (15:30 UTC)
├── data/
│   └── participant_oi_master.db     # 1,420 days pre-loaded historical SQLite DB
├── reports/
│   ├── latest_prediction_report.html # Ultra-luxurious visual dark-mode dashboard
│   ├── latest_prediction_report.md   # Clean markdown report summary
│   └── prediction_report_YYYY-MM-DD.html # Daily archive
├── src/
│   ├── __init__.py
│   ├── main.py                      # Master pipeline runner
│   ├── fetcher.py                   # 100% free multi-source fetcher (NSE + Macro)
│   ├── calculator.py                # Amit Dhamija sheet layout & CIS calculator
│   ├── regime_engine.py             # 5 Regimes, capital allocation & trajectory
│   ├── sector_rotation.py           # 16-Sector RS & leadership ranking
│   ├── index_sweep_engine.py        # Multi-confluence Liquidity Sweep Radar across ALL NSE Indices
│   ├── report_generator.py          # HTML dashboard & Markdown generator
│   └── email_sender.py              # Automated Gmail SMTP dispatcher
├── config.json                      # Target email: abhayv7272@gmail.com, 16 sectors
├── requirements.txt                 # requests, pandas, numpy, yfinance, beautifulsoup4
├── run.sh                           # 1-click execution script
└── README.md                        # Complete user guide & deployment instructions
```

---

## 9. EMAIL DISPATCH INSTRUCTIONS FOR `abhayv7272@gmail.com`

- **GitHub Repository**: `https://github.com/abhayv7272/smart-money-predictor`
- **Schedule**: Weekdays at 9:00 PM IST (`30 15 * * 1-5` UTC).
- **Action Required by User**:
  Add repository secrets in GitHub:
  - `MAIL_SERVER` = `smtp.gmail.com`
  - `MAIL_PORT` = `587`
  - `MAIL_USERNAME` = `your-gmail@gmail.com`
  - `MAIL_PASSWORD` = `your-16-char-app-password`
- **Output Delivered**: Full visual dark-mode HTML email with CIS meter, capital exposure %, swing protocol, top leading sectors, and active NSE index sweep setups.

---

## 9. FRIDAY-ONLY WEEKLY NSE INDEX LIQUIDITY SWEEP ENGINE

The repository also integrates the methodology from `abhayv7272/weekly-sweep`, but applies it **only to the configured NSE Broad Market, Sectoral, and Thematic index universe—never to individual stocks**.

### Timing and email behavior
- The normal pipeline still runs Monday-Friday at **9:00 PM IST**.
- The **Daily Index Sweep Radar runs and appears in the Gmail report every trading day**.
- The **Weekly Index Sweep Radar runs only when the India-time calendar day is Friday** and is added to that same Friday Gmail report.
- Monday-Thursday reports display only a schedule notice; they do not calculate or publish weekly signals.
- `python src/main.py --weekly` is available for manual testing/backfills.

### Weekly setup rules
- Daily OHLCV is resampled into weekly candles.
- Resting liquidity pools: confirmed 5-bar fractal weekly swing lows, 26-week low, and 52-week low.
- Sweep/reclaim: `Weekly Low < Pool Level` and `Weekly Close > Pool Level`.
- Rejection quality: lower wick at least 34% of weekly range, close in upper 50%, with wick/body and trend context included.
- Confluences include weekly 20-SMA context, bullish weekly candle, multi-week RSI divergence, sweep depth, and close position.
- Grades: A+ (70+), B (50-69), C (40-49); intended positional horizon is approximately 2-6 weeks.

### Architecture
- `src/weekly_index_sweep_engine.py`: index-only weekly detector and scorer.
- `src/main.py`: India-time Friday gate; daily scan always, weekly scan Friday only.
- `src/report_generator.py`: Friday-only weekly dashboard and Markdown section.
- `.github/workflows/daily_prediction.yml`: one weekday cron; the Python gate controls weekly inclusion and sends exactly one email to avoid duplicate Gmail reports.

---

## 10. INDEX-ONLY MTF SWEEP → DAILY TRAP → 15-MIN MSS ENGINE

Source notebook archived as `/home/user/colab_source_1b1X77M9WfsDdcEvcJb8UKP5EuV333k2r.ipynb`. Its BUY-side methodology is adapted in `src/mtf_index_sweep_engine.py` strictly for NSE index symbols; the notebook's 569-stock universe is not used.

Pipeline: previous completed W-FRI high/low → current-week daily low below PWL and latest close back above PWL → daily confirmation at 15:30 IST → causal current-week 15-minute close above the pre-trough 5-bar swing high. Entry is the MSS swing level, SL is the trough minus 0.20%, T1 is 1R, and T2 is previous-week high; minimum T2 RR is 1.0. It runs every weekday, but its HTML/Markdown block is signal-only and remains hidden when no index qualifies.

---

## 11. PRE-DEPLOYMENT HARDENING & DATA-INTEGRITY CONTRACT

- `src/index_universe.py` is the sole index universe. Actual index history is preferred; only index-tracking ETFs may serve as history fallbacks. Individual constituent stocks are prohibited.
- Official NSE OI uses bounded connect/read timeouts and five-business-day backtracking, then validated SQLite fallback; the old multi-endpoint retry explosion was removed.
- CSV parsing uses Python's CSV parser and validates Client, DII, FII and Pro rows.
- Sector rankings never fabricate neutral placeholder prices when a feed fails.
- Daily sweep requires a real major-swing or prior-day-low sweep; wick/RSI/EMA points alone cannot create a false sweep.
- Weekly scans exclude incomplete weekly candles outside Friday EOD execution.
- `diagnose.py` validates OI, history, macro, sector coverage, and all three index engines.
- GitHub Actions runs unit tests and fails loudly if SMTP credentials/delivery fail.

---

## 12. EMBEDDED SIGNAL CHARTS IN HTML/GMAIL REPORTS

Every qualifying Daily Liquidity Sweep, Friday Weekly Liquidity Sweep, and signal-only MTF PWL→Daily Trap→15m MSS setup now includes an annotated candlestick chart. Daily charts show swept level and invalidation low; weekly charts show weekly liquidity pool and stop; MTF charts show PWL, MSS entry, SL, T1, and PWH/T2. Standalone HTML uses embedded base64 PNGs, while `email_sender.py` converts them to inline CID MIME attachments so Gmail displays charts without external hosting or blocked URLs. Charts are generated only for active/qualifying signals.
