class RegimeEngine:
    def __init__(self, config_thresholds=None):
        self.thresholds = config_thresholds or {
            "fii_capitulation_ratio": 20.0,
            "fii_accumulation_max": 40.0,
            "fii_trend_markup_max": 70.0,
            "fii_overbought_ratio": 78.0
        }

    def evaluate_regime_and_action(self, calc_result, macro_data=None, nifty_current_price=None):
        cis = calc_result["cis_score"]
        fii_ratio = calc_result["fii_long_ratio"]
        fii_stk_3d = calc_result["fii_stk_flow_3d"]
        
        # 1. Regime Classification
        if fii_ratio < self.thresholds["fii_capitulation_ratio"]:
            regime_id = 1
            regime_name = "Regime 1: Capitulation & Short Exhaustion"
            regime_desc = "FIIs are heavily net short (extreme pessimism). Smart Money short capacity is exhausted. High probability of multi-week bottom formation."
            regime_color = "#3B82F6" # Blue
            capital_allocation_pct = 100
            cash_reserve_pct = 0
            primary_signal = "STRONGLY BUY"
            action_badge = "STRONGLY_BUY"
            signal_color = "#10B981"
            action_instructions = "Deploy 100% capital into high-beta, leading fundamental stocks at support / 20 EMA reclaim. Target 20 to 40 day positional swing holding."
            
        elif fii_ratio < self.thresholds["fii_accumulation_max"]:
            regime_id = 2
            regime_name = "Regime 2: Accumulation & Early Breakout"
            regime_desc = "FIIs are covering shorts and accumulating fresh stock futures. Broad market entering Stage-2 markup."
            regime_color = "#10B981" # Green
            capital_allocation_pct = 85
            cash_reserve_pct = 15
            primary_signal = "STRONGLY BUY" if cis >= 3.0 else "BUY / ADD"
            action_badge = "STRONGLY_BUY" if cis >= 3.0 else "BUY_ADD"
            signal_color = "#10B981"
            action_instructions = "Aggressive swing buying on Stage-2 stock breakouts. Keep 15% cash buffer. Trail stops with 20 EMA."
            
        elif fii_ratio <= self.thresholds["fii_trend_markup_max"]:
            regime_id = 3
            regime_name = "Regime 3: Full Momentum Markup"
            regime_desc = "Institutional trend is healthy and active. Steady accumulation across broader market equities."
            regime_color = "#059669" # Emerald
            if cis >= 3.0:
                capital_allocation_pct = 80
                cash_reserve_pct = 20
                primary_signal = "BUY / ADD"
                action_badge = "BUY_ADD"
                signal_color = "#10B981"
                action_instructions = "Add to leading sector winners on shallow 2-3 day pullbacks. Trail existing winners."
            elif cis >= -1.0:
                capital_allocation_pct = 70
                cash_reserve_pct = 30
                primary_signal = "HOLD & TRAIL SL"
                action_badge = "HOLD"
                signal_color = "#F59E0B"
                action_instructions = "Hold existing swing positions. Move SL to cost on trades up +10%. Lock 50% profit at +20%."
            else:
                capital_allocation_pct = 50
                cash_reserve_pct = 50
                primary_signal = "PARTIAL PROFIT / REDUCE"
                action_badge = "REDUCE"
                signal_color = "#F97316"
                action_instructions = "Tighten stop losses. Institutional flow is showing temporary distribution. Avoid fresh breakout buys."
                
        elif fii_ratio <= self.thresholds["fii_overbought_ratio"]:
            regime_id = 4
            regime_name = "Regime 4: Overbought Distribution Alert"
            regime_desc = "FIIs are heavily long (>70%). Retail euphoria is high. Smart Money is beginning to distribute stock inventory."
            regime_color = "#F97316" # Orange
            capital_allocation_pct = 35
            cash_reserve_pct = 65
            primary_signal = "PARTIAL PROFIT / REDUCE"
            action_badge = "REDUCE"
            signal_color = "#F97316"
            action_instructions = "Raise 65% cash. Book profits in high-beta swings. Do not initiate fresh positional longs."
            
        else: # FII Ratio > 78%
            regime_id = 5
            regime_name = "Regime 5: Extreme Market Top / Markdown Warning"
            regime_desc = "FII Long Ratio is in extreme overbought territory (>78%). Maximum vulnerability to sudden 1000-2000 pt corrections."
            regime_color = "#EF4444" # Red
            capital_allocation_pct = 10
            cash_reserve_pct = 90
            primary_signal = "STRONGLY SELL / 100% CASH"
            action_badge = "STRONGLY_SELL"
            signal_color = "#EF4444"
            action_instructions = "Exit all high-risk swing positions. Sit 90%-100% in cash. Capital preservation is priority #1."

        # Macro Override if Crude or Yields are spiking violently
        macro_warnings = []
        if macro_data:
            def valid_macro_value(key):
                entry = macro_data.get(key, {})
                if entry.get("status") == "unavailable":
                    return None
                raw = entry.get("current")
                try:
                    value = float(raw)
                    return value if value == value and abs(value) != float("inf") else None
                except (TypeError, ValueError):
                    return None

            crude = valid_macro_value("brent_crude")
            yield_10y = valid_macro_value("us_10y_yield")
            dxy = valid_macro_value("us_dollar_index")
            if crude is not None and crude > 95.0:
                macro_warnings.append(f"Brent Crude elevated at ${crude:.2f}/bbl (Pressure on INR & Auto/Paints margins)")
            if yield_10y is not None and yield_10y > 4.75:
                macro_warnings.append(f"US 10Y Yields high at {yield_10y:.2f}% (Risk of foreign capital outflows)")
            if dxy is not None and dxy > 105.0:
                macro_warnings.append(f"US Dollar Index strong at {dxy:.2f} (Emerging market currency headwind)")

        # Nifty levels must be anchored to an actual fresh index value. Never use a
        # hard-coded spot/levels when the feed is missing.
        try:
            px = float(nifty_current_price)
            has_spot = px > 1000 and px == px and abs(px) != float("inf")
        except (TypeError, ValueError):
            px, has_spot = None, False
        if has_spot:
            sup1 = round(px - px * 0.0075, -1)
            sup2 = round(px - px * 0.015, -1)
            sweep_zone = round(sup1 - 35, 0)
            res1 = round(px + px * 0.008, -1)
            res2 = round(px + px * 0.018, -1)
        else:
            sup1 = sup2 = sweep_zone = res1 = res2 = "Unavailable"

        if cis >= 3.0:
            trajectory_type = "BULLISH_EXPANSION"
            trajectory = (
                f"Constructive Bullish Flow: expected consolidation/liquidity sweep near {sweep_zone}-{sup1}, "
                f"then expansion towards {res1} and {res2}." if has_spot else
                "Constructive institutional flow; numerical NIFTY levels are unavailable because no fresh spot feed was validated."
            )
        elif cis <= -3.0:
            trajectory_type = "BEARISH_BREAKDOWN"
            trajectory = (
                f"Heavy Bearish Flow: rejection near resistance {res1}, with support {sup1} at risk and potential breakdown towards {sup2}."
                if has_spot else
                "Heavy bearish institutional flow; numerical NIFTY levels are unavailable because no fresh spot feed was validated."
            )
        else:
            trajectory_type = "RANGE_BOUND"
            trajectory = (
                f"Sideways Range Bound: market expected between support {sup1} and resistance {res1}; favour selective stock picking."
                if has_spot else
                "Institutional flow is range-bound; numerical NIFTY support/resistance is unavailable because no fresh spot feed was validated."
            )

        return {
            "regime_id": regime_id,
            "regime_name": regime_name,
            "regime_desc": regime_desc,
            "regime_color": regime_color,
            "capital_allocation_pct": capital_allocation_pct,
            "cash_reserve_pct": cash_reserve_pct,
            "primary_signal": primary_signal,
            "action_badge": action_badge,
            "signal_color": signal_color,
            "action_instructions": action_instructions,
            "macro_warnings": macro_warnings,
            "support_1": sup1,
            "support_2": sup2,
            "sweep_zone": sweep_zone,
            "resistance_1": res1,
            "resistance_2": res2,
            "trajectory": trajectory,
            "trajectory_type": trajectory_type
        }
