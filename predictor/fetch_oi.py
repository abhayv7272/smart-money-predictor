#!/usr/bin/env python3
"""
NSE participant-wise OI fetcher — 3 free routes with fallback:
  1. Direct NSE (browser headers)  2. r.jina.ai proxy  3. urltomarkdown proxy
Appends parsed rows to data/participant_oi_master.csv (idempotent).
"""
import re, csv, time, datetime as dt, urllib.parse
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "participant_oi_master.csv"
NSE_URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{tag}.csv"
COLS = ["future_index_long","future_index_short","future_stock_long","future_stock_short",
        "option_index_call_long","option_index_put_long","option_index_call_short","option_index_put_short",
        "option_stock_call_long","option_stock_put_long","option_stock_call_short","option_stock_put_short",
        "total_long_contracts","total_short_contracts"]
HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/csv,*/*", "Referer": "https://www.nseindia.com/"}

ROW_RE = re.compile(r"\b(Client|DII|FII|Pro|TOTAL)\b((?:\s*,\s*\"?[\d,]+\"?){14})")

def parse_body(txt: str):
    """Works even when proxy collapses newlines. Returns 5 rows or None."""
    if "Participant wise" not in txt and "Future Index Long" not in txt:
        return None
    txt = txt.replace('"', "")
    rows = {}
    for m in ROW_RE.finditer(txt):
        who = m.group(1)
        nums = [int(x.strip()) for x in m.group(2).strip().lstrip(",").split(",") if x.strip()]
        if len(nums) == 14 and who not in rows:
            rows[who] = nums
    if set(rows) != {"Client", "DII", "FII", "Pro", "TOTAL"}:
        return None
    return rows

def _direct(url):
    s = requests.Session(); s.headers.update(HDRS)
    try: s.get("https://www.nseindia.com", timeout=10)
    except Exception: pass
    r = s.get(url, timeout=20)
    return r.text if r.status_code == 200 else None

def _jina(url):
    r = requests.get("https://r.jina.ai/" + url, timeout=40)
    if r.status_code != 200: return None
    body = r.text
    return body.split("Markdown Content:", 1)[-1] if "Markdown Content:" in body else body

def _u2m(url):
    r = requests.get("https://urltomarkdown.herokuapp.com/?url=" + urllib.parse.quote(url, safe=""),
                     timeout=40)
    return r.text if r.status_code == 200 else None

def fetch_date(d: dt.date, tries=3):
    """Returns dict rows for date d, or None (holiday/not published yet)."""
    url = NSE_URL.format(tag=d.strftime("%d%m%Y"))
    for attempt in range(tries):
        for route in (_direct, _jina, _u2m):
            try:
                body = route(url)
            except Exception:
                body = None
            if body:
                if "error 404" in body.lower() or "404 Not Found" in body:
                    return None  # holiday / not yet published
                rows = parse_body(body)
                if rows:
                    return rows
        if attempt < tries - 1:
            time.sleep(15 * (attempt + 1))
    return None

def existing_dates():
    if not MASTER.exists(): return set()
    with open(MASTER) as f:
        return {line.split(",", 1)[0] for line in f if line[:2] == "20"}

def append_rows(d: dt.date, rows):
    have_header = MASTER.exists() and MASTER.stat().st_size > 0
    with open(MASTER, "a", newline="") as f:
        w = csv.writer(f)
        if not have_header:
            w.writerow(["date", "client_type"] + COLS)
        for who in ["Client", "DII", "FII", "Pro", "TOTAL"]:
            w.writerow([d.isoformat(), who] + rows[who])

def ist_today():
    """GitHub Actions UTC par chalta hai — hamesha IST ki date use karo (BUG FIX)."""
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()

def update_master(lookback_days=7):
    """Fetch any missing recent trading days. Returns list of dates added."""
    have = existing_dates()
    added = []
    today = ist_today()
    for i in range(lookback_days, -1, -1):
        d = today - dt.timedelta(days=i)
        if d.weekday() >= 5 or d.isoformat() in have:
            continue
        rows = fetch_date(d)
        if rows:
            append_rows(d, rows)
            added.append(d.isoformat())
            print(f"[fetch] added {d}")
        else:
            print(f"[fetch] {d}: no data (holiday / not published / blocked)")
    return added

if __name__ == "__main__":
    print("added:", update_master())
