import os
import urllib.request
import datetime
import sqlite3
import pandas as pd
import yfinance as yf
import json
import time
import random
import requests
import csv
from io import StringIO
from index_universe import INDEX_UNIVERSE, symbols_for_history
from zoneinfo import ZoneInfo

class FreeDataFetcher:
    def __init__(self, config_path="config.json", db_path="data/participant_oi_master.db"):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = os.path.join(self.base_dir, config_path)
        self.db_path = os.path.join(self.base_dir, db_path)
        
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {
                "recipient_email": "abhayv7272@gmail.com",
                "sectors": [],
                "macro_tickers": {}
            }
            
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        ]

    def _get_headers(self):
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive"
        }

    def fetch_latest_participant_oi(self, target_date=None):
        """Fetch latest official NSE participant OI without pathological retry delays.

        Only primary official archive is tried for recent business dates. A short connect/read
        timeout prevents one unpublished file from blocking the entire GitHub job. The verified
        SQLite cache is the deterministic fallback.
        """
        cur_date = target_date or datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date()
        print(f"[INFO] Scanning official NSE Participant OI from: {cur_date}")
        session = requests.Session()
        # At most five business dates; primary archive is authoritative and normally available.
        checked = 0
        for offset in range(10):
            d = cur_date - datetime.timedelta(days=offset)
            if d.weekday() >= 5: continue
            checked += 1
            if checked > 5: break
            ds=d.strftime("%d%m%Y")
            url=f"https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{ds}.csv"
            try:
                r=session.get(url,headers=self._get_headers(),timeout=(3.05,5))
                text=r.content.decode("utf-8-sig",errors="ignore")
                if r.status_code==200 and "Client Type" in text and len(text)>300:
                    records=self._parse_participant_csv(text,d.isoformat())
                    if records and {x["client_type"] for x in records}>={"Client","DII","FII","Pro"}:
                        self._save_to_db(records)
                        print(f"[SUCCESS] Official NSE OI {d.isoformat()} ({len(records)} rows)")
                        return {"date":d.isoformat(),"display_date":d.strftime("%d %B %Y"),
                                "raw_data":records,"status":"success","source":"live_nse_exchange","url":url}
            except requests.RequestException as e:
                print(f"[WARN] NSE archive {d.isoformat()}: {type(e).__name__}")
        print("[WARNING] Using latest validated SQLite OI cache.")
        return self._get_latest_from_db()

    def _parse_participant_csv(self, content, date_str):
        rows=list(csv.reader(StringIO(content)))
        header=next((i for i,r in enumerate(rows[:10]) if r and r[0].strip()=="Client Type"),None)
        if header is None:return None
        fields=["future_index_long","future_index_short","future_stock_long","future_stock_short",
                "option_index_call_long","option_index_put_long","option_index_call_short","option_index_put_short",
                "option_stock_call_long","option_stock_put_long","option_stock_call_short","option_stock_put_short",
                "total_long_contracts","total_short_contracts"]
        records=[]
        for row in rows[header+1:]:
            if len(row)<15:continue
            typ=row[0].strip()
            if typ not in {"Client","DII","FII","Pro","TOTAL"}:continue
            try:
                vals=[int(str(v).strip().replace(",","").replace('"',"")) for v in row[1:15]]
            except (ValueError,TypeError):continue
            rec={"date":date_str,"client_type":typ};rec.update(dict(zip(fields,vals)));records.append(rec)
        return records

    def _save_to_db(self, records):
        if not records:return
        try:
            os.makedirs(os.path.dirname(self.db_path),exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='participant_oi_raw'").fetchone()
                if exists:conn.execute("DELETE FROM participant_oi_raw WHERE date = ?",(records[0]["date"],))
                pd.DataFrame(records).to_sql("participant_oi_raw",conn,if_exists="append",index=False)
        except Exception as e:
            print(f"[DB_ERROR] Failed to cache to SQLite: {e}")

    def _get_latest_from_db(self):
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database {self.db_path} not found.")
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql("SELECT * FROM participant_oi_raw ORDER BY date DESC LIMIT 20", conn)
        conn.close()
        if df.empty:
            raise ValueError("No participant data found in database.")
        latest_date = df["date"].iloc[0]
        records = df[df["date"] == latest_date].to_dict(orient="records")
        return {
            "date": latest_date,
            "display_date": pd.to_datetime(latest_date).strftime("%d %B %Y"),
            "raw_data": records,
            "status": "success",
            "source": "sqlite_cache_latest"
        }

    def fetch_recent_history(self, days_count=15):
        """Fetches the last N trading days from SQLite for multi-day delta calculations."""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql(f"""
            SELECT * FROM participant_oi_raw 
            WHERE date IN (
                SELECT DISTINCT date FROM participant_oi_raw ORDER BY date DESC LIMIT {days_count}
            )
            ORDER BY date ASC
        """, conn)
        conn.close()
        return df

    def fetch_global_macro(self):
        """Fetches live/EOD Brent crude, US 10Y yields, DXY, and US Market performance with fallbacks."""
        macro_dict = {}
        fallback_map = {
            "brent_crude": ["BZ=F", "CL=F"],
            "us_10y_yield": ["^TNX", "10Y"],
            "us_dollar_index": ["DX-Y.NYB", "UUP"],
            "dow_jones": ["^DJI", "DIA"],
            "sp500": ["^GSPC", "SPY"],
            "nifty_50": ["^NSEI", "NIFTYBEES.NS"],
            "bank_nifty": ["^NSEBANK", "BANKBEES.NS"]
        }

        for key, tickers in fallback_map.items():
            val = {"symbol": tickers[0], "current": 0.0, "previous": 0.0, "change_pct": 0.0}
            for sym in tickers:
                try:
                    t = yf.Ticker(sym)
                    h = t.history(period="5d")
                    if not h.empty and len(h) >= 2:
                        curr_px = float(h["Close"].iloc[-1])
                        prev_px = float(h["Close"].iloc[-2])
                        chg_pct = float((curr_px / prev_px - 1) * 100)
                        val = {
                            "symbol": sym,
                            "current": round(curr_px, 2),
                            "previous": round(prev_px, 2),
                            "change_pct": round(chg_pct, 2)
                        }
                        break
                except Exception:
                    continue
            macro_dict[key] = val
        return macro_dict

    def fetch_sector_strength(self):
        """Relative-strength data for index names using actual index or index-tracking ETF only.

        Failed feeds are omitted and reported in logs; fabricated neutral placeholders are never
        emitted because they silently corrupt rankings.
        """
        def history(item):
            for sym in symbols_for_history(item):
                try:
                    h=yf.download(sym,period="3mo",interval="1d",progress=False,timeout=8)
                    if isinstance(h.columns,pd.MultiIndex):h.columns=h.columns.get_level_values(0)
                    h=h.dropna(subset=["Close"])
                    if len(h)>=22:return h,sym
                except Exception:pass
            return pd.DataFrame(),None

        bench_item=next(x for x in INDEX_UNIVERSE if x["name"]=="Nifty 50")
        bh,bs=history(bench_item)
        if len(bh)<22:
            print("[WARN] Nifty benchmark unavailable; sector RS cannot be computed safely.")
            return []
        b1w=float((bh.Close.iloc[-1]/bh.Close.iloc[-5]-1)*100)
        b1m=float((bh.Close.iloc[-1]/bh.Close.iloc[-22]-1)*100)
        result=[]
        # Keep sector-rotation scope to broad mid/small plus sectoral indices; omit duplicate thematic rows.
        selected=[x for x in INDEX_UNIVERSE if x["category"]=="Sectoral" or x["name"] in {"Nifty Midcap 50","Nifty Smallcap 250"}]
        for item in selected:
            h,sym=history(item)
            if len(h)<22:
                print(f"[WARN] Sector index feed unavailable: {item['name']}")
                continue
            cur=float(h.Close.iloc[-1]);d=float((cur/h.Close.iloc[-2]-1)*100)
            w=float((cur/h.Close.iloc[-5]-1)*100);m=float((cur/h.Close.iloc[-22]-1)*100)
            ema=float(h.Close.ewm(span=20,adjust=False).mean().iloc[-1]);above=cur>=ema*.995
            rs=round((w-b1w)+(m-b1m)*.5,2)
            if rs>2 and above:status,code="LEADER (Strong Outperformance)","LEADER"
            elif rs>0:status,code="IMPROVING (Outperforming)","IMPROVING"
            elif rs>-2.5:status,code="NEUTRAL (In Line)","NEUTRAL"
            else:status,code="LAGGARD (Underperforming)","LAGGARD"
            result.append({"name":item["name"],"ticker":sym,
                "data_source":"actual_index" if sym==item.get("index_symbol") else "index_tracking_etf",
                "description":item["description"],"current":round(cur,2),"chg_1d":round(d,2),
                "chg_1w":round(w,2),"chg_1m":round(m,2),"above_20_ema":bool(above),
                "rs_score":rs,"status":status,"status_code":code})
        return sorted(result,key=lambda x:x["rs_score"],reverse=True)
