import pandas as pd


_REQUIRED_OI_FIELDS = (
    "future_index_long", "future_index_short", "future_stock_long", "future_stock_short",
    "option_index_call_long", "option_index_put_long", "option_index_call_short", "option_index_put_short",
    "option_stock_call_long", "option_stock_put_long", "option_stock_call_short", "option_stock_put_short",
    "total_long_contracts", "total_short_contracts",
)
_REQUIRED_PARTICIPANTS = {"Client", "DII", "FII", "Pro"}


class InstitutionalCalculator:
    def __init__(self, raw_history_df):
        if raw_history_df is None or raw_history_df.empty:
            raise ValueError("Participant OI history is empty.")
        required = {"date", "client_type", *_REQUIRED_OI_FIELDS}
        missing = required - set(raw_history_df.columns)
        if missing:
            raise ValueError(f"Participant OI history is missing fields: {', '.join(sorted(missing))}")

        self.raw_df = raw_history_df.copy()
        parsed_dates = pd.to_datetime(self.raw_df["date"], errors="coerce")
        if parsed_dates.isna().any():
            raise ValueError("Participant OI history contains invalid dates.")
        self.raw_df["date"] = parsed_dates.dt.strftime("%Y-%m-%d")
        self.raw_df["client_type"] = self.raw_df["client_type"].astype(str).str.strip()
        if self.raw_df.duplicated(["date", "client_type"]).any():
            raise ValueError("Participant OI history contains duplicate rows for a date/type.")
        for field in _REQUIRED_OI_FIELDS:
            self.raw_df[field] = pd.to_numeric(self.raw_df[field], errors="coerce")
            if self.raw_df[field].isna().any() or (self.raw_df[field] < 0).any():
                raise ValueError(f"Participant OI history has invalid values in {field}.")
        for date_value, group in self.raw_df.groupby("date", sort=False):
            present = set(group["client_type"])
            if not _REQUIRED_PARTICIPANTS.issubset(present):
                raise ValueError(f"Participant OI data for {date_value} is incomplete.")
        self.dates = sorted(self.raw_df["date"].unique())
        # Only the latest six dates feed the displayed 3-/5-session flows; older archive
        # gaps are irrelevant and should not block a later, newly continuous run.
        flow_dates = self.dates[-6:]
        for previous, current in zip(flow_dates, flow_dates[1:]):
            gap = (pd.Timestamp(current) - pd.Timestamp(previous)).days
            if gap > 10:
                raise ValueError(
                    f"Recent participant OI history has a {gap}-day gap between {previous} and {current}; "
                    "multi-day flows cannot be calculated across it."
                )
        
    def calculate_latest_sheet(self):
        """
        Builds Amit Dhamija Excel layout with Ultra-Enhanced Multi-Timeframe Flow:
        - Multi-session Carried Inventory (latest session, previous session, T-2 when available)
        - Positions Bought / Sold Today (Added/Closed Longs & Shorts)
        - 3-Day & 5-Day Cumulative Institutional Thrust
        - 6-Factor Composite Institutional Score (-10 to +10)
        - High-Probability Trap Detection
        """
        if len(self.dates) < 3:
            raise ValueError("Need at least 3 trading sessions of participant data.")
            
        t0_date = self.dates[-1] # Latest session
        t1_date = self.dates[-2] # Previous session
        t2_date = self.dates[-3] # Two sessions ago
        
        df_t0 = self.raw_df[self.raw_df["date"] == t0_date].set_index("client_type")
        df_t1 = self.raw_df[self.raw_df["date"] == t1_date].set_index("client_type")
        df_t2 = self.raw_df[self.raw_df["date"] == t2_date].set_index("client_type")
        
        instruments = [
            ("Index Futures", "future_index_long", "future_index_short", False),
            ("Index Calls", "option_index_call_long", "option_index_call_short", False),
            ("Index Puts", "option_index_put_long", "option_index_put_short", True),
            ("Stock Futures", "future_stock_long", "future_stock_short", False),
            ("Stock Calls", "option_stock_call_long", "option_stock_call_short", False),
            ("Stock Puts", "option_stock_put_long", "option_stock_put_short", True)
        ]
        
        participants = ["Client", "DII", "FII", "Pro"]
        sheet_sections = {}
        for inst_label, long_col, short_col, is_put in instruments:
            part_rows = []
            for p in participants:
                l0 = int(df_t0.loc[p, long_col]) if p in df_t0.index else 0
                s0 = int(df_t0.loc[p, short_col]) if p in df_t0.index else 0
                l1 = int(df_t1.loc[p, long_col]) if p in df_t1.index else 0
                s1 = int(df_t1.loc[p, short_col]) if p in df_t1.index else 0
                l2 = int(df_t2.loc[p, long_col]) if p in df_t2.index else 0
                s2 = int(df_t2.loc[p, short_col]) if p in df_t2.index else 0
                
                d_long = l0 - l1
                d_short = s0 - s1
                net_today = d_long - d_short
                carried_t0 = l0 - s0
                carried_t1 = l1 - s1
                carried_t2 = l2 - s2
                
                long_action = f"Added Longs: +{d_long:,}" if d_long >= 0 else f"Closed Longs: {d_long:,}"
                short_action = f"Added Shorts: +{d_short:,}" if d_short >= 0 else f"Closed Shorts: {d_short:,}"
                net_action = f"Bought Net: +{net_today:,}" if net_today >= 0 else f"Sold Net: {net_today:,}"
                
                if not is_put:
                    sentiment = "BULLISH" if net_today > 0 else "BEARISH" if net_today < 0 else "NEUTRAL"
                    carried_sentiment = "BULLISH" if carried_t0 > 0 else "BEARISH" if carried_t0 < 0 else "NEUTRAL"
                else:
                    sentiment = "BEARISH" if net_today > 0 else "BULLISH" if net_today < 0 else "NEUTRAL"
                    carried_sentiment = "BULLISH" if carried_t0 < 0 else "BEARISH" if carried_t0 > 0 else "NEUTRAL"
                
                part_rows.append({
                    "participant": p,
                    "d_long": d_long,
                    "long_action": long_action,
                    "d_short": d_short,
                    "short_action": short_action,
                    "net_today": net_today,
                    "net_action": net_action,
                    "sentiment": sentiment,
                    "carried_t0": carried_t0,
                    "carried_t1": carried_t1,
                    "carried_t2": carried_t2,
                    "carried_sentiment": carried_sentiment
                })
            sheet_sections[inst_label] = part_rows
            
        fii_il = int(df_t0.loc["FII", "future_index_long"])
        fii_is = int(df_t0.loc["FII", "future_index_short"])
        tot_fii_idx = fii_il + fii_is
        if tot_fii_idx <= 0:
            raise ValueError("FII index-futures long/short total is zero; ratio is undefined.")
        fii_long_ratio = round(fii_il / tot_fii_idx * 100, 2)

        # Daily net-position changes are exact differences between adjacent OI dates.
        # Never multiply one observed change to fabricate a 3- or 5-session total.
        stk_flows = []
        for i in range(min(5, len(self.dates) - 1)):
            d_cur = self.dates[-(i + 1)]
            d_prev = self.dates[-(i + 2)]
            sub_c = self.raw_df[self.raw_df["date"] == d_cur].set_index("client_type")
            sub_p = self.raw_df[self.raw_df["date"] == d_prev].set_index("client_type")
            fii_cur_net = sub_c.loc["FII", "future_stock_long"] - sub_c.loc["FII", "future_stock_short"]
            fii_prev_net = sub_p.loc["FII", "future_stock_long"] - sub_p.loc["FII", "future_stock_short"]
            stk_flows.append(int(fii_cur_net - fii_prev_net))

        sample_3d = min(3, len(stk_flows))
        sample_5d = min(5, len(stk_flows))
        flow_3d_complete = sample_3d == 3
        flow_5d_complete = sample_5d == 5
        # Use None for unavailable windows instead of a fabricated zero. A complete
        # three-session flow can still contribute when the five-session window is short.
        fii_stk_flow_3d = sum(stk_flows[:3]) if flow_3d_complete else None
        fii_stk_flow_5d = sum(stk_flows[:5]) if flow_5d_complete else None
        
        cis_score, cis_breakdown = self._compute_cis(sheet_sections, fii_long_ratio, fii_stk_flow_3d, fii_stk_flow_5d)
        traps = self._detect_traps(sheet_sections, fii_long_ratio)
        
        return {
            "date": t0_date,
            "display_date": pd.to_datetime(t0_date).strftime("%d %B %Y"),
            "fii_long_ratio": fii_long_ratio,
            "fii_stk_flow_3d": fii_stk_flow_3d,
            "fii_stk_flow_5d": fii_stk_flow_5d,
            "fii_stk_flow_3d_sample_days": sample_3d,
            "fii_stk_flow_5d_sample_days": sample_5d,
            "fii_stk_flow_3d_complete": flow_3d_complete,
            "fii_stk_flow_5d_complete": flow_5d_complete,
            "sheet_sections": sheet_sections,
            "cis_score": cis_score,
            "cis_breakdown": cis_breakdown,
            "traps": traps
        }

    def _compute_cis(self, sections, fii_ratio, fii_stk_3d, fii_stk_5d):
        score = 0.0
        breakdown = []
        
        # 1. FII Index Futures Flow (Weight: 2.0)
        fii_idx = next(r for r in sections["Index Futures"] if r["participant"] == "FII")
        if fii_idx["net_today"] > 5000:
            score += 2.0
            breakdown.append(("FII Index Futures Buying (+)", +2.0))
        elif fii_idx["net_today"] < -5000:
            score -= 2.0
            breakdown.append(("FII Index Futures Selling (-)", -2.0))
            
        # 2. FII Stock Futures Thrust (5-day weight: 3.0; 3-day fallback: 2.0).
        # Missing windows are None and must not be interpreted as measured zero flow.
        if fii_stk_5d is not None and fii_stk_5d > 45000:
            score += 3.0
            breakdown.append(("FII Mega 5-Day Stock Accumulation Wave (+)", +3.0))
        elif fii_stk_3d is not None and fii_stk_3d > 20000:
            score += 2.0
            breakdown.append(("FII 3-Day Stock Accumulation (+)", +2.0))
        elif fii_stk_5d is not None and fii_stk_5d < -45000:
            score -= 3.0
            breakdown.append(("FII Mega 5-Day Stock Distribution Wave (-)", -3.0))
        elif fii_stk_3d is not None and fii_stk_3d < -20000:
            score -= 2.0
            breakdown.append(("FII 3-Day Stock Distribution (-)", -2.0))
            
        # 3. PRO Desks Options Delta (Weight: 2.0)
        pro_call = next(r for r in sections["Index Calls"] if r["participant"] == "Pro")
        pro_put = next(r for r in sections["Index Puts"] if r["participant"] == "Pro")
        
        if pro_call["net_today"] > 15000:
            score += 1.0
            breakdown.append(("PRO Index Call Buying (+)", +1.0))
        elif pro_call["net_today"] < -15000:
            score -= 1.0
            breakdown.append(("PRO Index Call Writing (-)", -1.0))
            
        if pro_put["net_today"] < -15000: # Sold Puts = Bullish Floor
            score += 1.0
            breakdown.append(("PRO Index Put Writing Floor (+)", +1.0))
        elif pro_put["net_today"] > 15000:
            score -= 1.0
            breakdown.append(("PRO Index Put Buying Hedge (-)", -1.0))
            
        # 4. Retail Contrarian Trap (Weight: 1.5)
        cli_call = next(r for r in sections["Index Calls"] if r["participant"] == "Client")
        cli_put = next(r for r in sections["Index Puts"] if r["participant"] == "Client")
        
        if cli_put["net_today"] > 35000 and pro_put["net_today"] < 0:
            score += 1.5
            breakdown.append(("Retail Panic Put Buying Squeeze Setup (+)", +1.5))
        elif cli_call["net_today"] > 35000 and pro_call["net_today"] < 0:
            score -= 1.5
            breakdown.append(("Retail Euphoric Call Buying Trap Warning (-)", -1.5))
            
        # 5. FII Long Ratio Extremes (Weight: 2.0)
        if fii_ratio < 20.0:
            score += 2.0
            breakdown.append(("FII Extreme Capitulation Bottom Zone (<20%) (+)", +2.0))
        elif fii_ratio > 78.0:
            score -= 2.0
            breakdown.append(("FII Extreme Overbought Distribution Zone (>78%) (-)", -2.0))
            
        score = max(-10.0, min(10.0, score))
        return round(score, 1), breakdown

    def _detect_traps(self, sections, fii_ratio):
        traps = []
        cli_put = next(r for r in sections["Index Puts"] if r["participant"] == "Client")
        pro_put = next(r for r in sections["Index Puts"] if r["participant"] == "Pro")
        fii_call = next(r for r in sections["Index Calls"] if r["participant"] == "FII")
        cli_call = next(r for r in sections["Index Calls"] if r["participant"] == "Client")
        pro_call = next(r for r in sections["Index Calls"] if r["participant"] == "Pro")
        
        if cli_put["net_today"] > 30000 and (pro_put["net_today"] < -10000 or fii_call["net_today"] > 10000):
            traps.append({
                "type": "BULLISH_SHORT_SQUEEZE",
                "title": "⚡ Nike-Swoosh Short Squeeze Alert",
                "description": "Retailers bought heavy Puts while Smart Money (FIIs/PROs) wrote Puts and bought Calls. Expected pattern: Morning dip below support to shake out retail, followed by an explosive V-shape rally.",
                "color": "#10B981"
            })
            
        if cli_call["net_today"] > 35000 and (pro_call["net_today"] < -10000 or fii_ratio > 75):
            traps.append({
                "type": "BEARISH_GAP_UP_TRAP",
                "title": "⚠️ Bull Trap / Sell-on-Rise Alert",
                "description": "Retailers accumulated heavy Call options in euphoria while Institutions took the sell side. Expected pattern: Morning gap-up followed by strong institutional rejection near resistance.",
                "color": "#EF4444"
            })
            
        if fii_ratio < 18.0:
            traps.append({
                "type": "MEGA_CAPITULATION_BOTTOM",
                "title": "🚀 Historic Capitulation Bottom Zone",
                "description": f"FII Long Ratio is at an extreme low of {fii_ratio}%. Smart Money short capacity is exhausted. Historically generates +8% to +15% multi-week swing rallies.",
                "color": "#3B82F6"
            })
            
        return traps
