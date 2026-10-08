#!/usr/bin/env python3
"""Daily updater for data/indices_ohlc.csv (ALL NSE indices OHLC).
Source: nsearchives.nseindia.com ind_close_all_DDMMYYYY.csv
Route 1: direct NSE (GitHub Actions runners se chalta hai, browser headers ke saath)
Route 2: r.jina.ai proxy fallback (sandbox/blocked IPs ke liye)
"""
import csv
import datetime as dt
import time
import io
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
F = ROOT / "data/indices_ohlc.csv"
BASE = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{tag}.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/csv,*/*", "Referer": "https://www.nseindia.com/"}
KEEP_DATES = 560   # ~2.2 saal (weekly scanner ko 104+ weekly candles chahiye)


def _get(url, tries=3):
    """Route 1 direct NSE; Route 2 jina proxy — har route par retry (BUG FIX: pehle
    single-shot tha, ek 429/timeout par pura din miss ho jata tha)."""
    for attempt in range(tries):
        # Route 1: direct
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200 and "Index Name" in r.text[:300]:
                return r.text
            if r.status_code == 404:
                return "404"
        except Exception:
            pass
        # Route 2: jina proxy
        try:
            r = requests.get("https://r.jina.ai/" + url, timeout=60)
            body = r.text
            if "error 404" in body[:2000].lower() or "404 Not Found" in body[:2000]:
                return "404"
            m = body.find("Markdown Content:")
            if m >= 0 and "Index Name" in body[m:m + 400]:
                return body[m + len("Markdown Content:"):].strip()
        except Exception:
            pass
        if attempt < tries - 1:
            time.sleep(20 * (attempt + 1))
    return None


def parse_rows(txt):
    rows = []
    rdr = csv.reader(io.StringIO(txt))
    header = next(rdr, None)
    if not header or "Index Name" not in header[0]:
        return rows
    for r in rdr:
        if len(r) < 10:
            continue
        # BUG FIX: NSE kabhi quoted comma-numbers deta hai ("12,345.67") — strip karo
        o, h, l, c, vol, turn = (x.replace(",", "").strip() for x in
                                 (r[2], r[3], r[4], r[5], r[8], r[9]))
        if "-" in (o, h, l, c) or not o or not c:
            continue
        try:
            rows.append(dict(
                Date=pd.to_datetime(r[1].strip(), format="%d-%m-%Y"),
                Index=r[0].strip(), Open=float(o), High=float(h), Low=float(l),
                Close=float(c),
                Volume=float(vol) if vol not in ("-", "") else None,
                TurnoverCr=float(turn) if turn not in ("-", "") else None))
        except ValueError:
            continue
    return rows


def update_indices(lookback_days=7):
    m = pd.read_csv(F, parse_dates=["Date"])
    have = set(m["Date"].dt.date)
    added = []
    # BUG FIX: Actions UTC par hai — IST date use karo
    today = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()
    for back in range(lookback_days, -1, -1):
        d = today - dt.timedelta(days=back)
        if d.weekday() >= 5 or d in have:
            continue
        txt = _get(BASE.format(tag=d.strftime("%d%m%Y")))
        if txt is None or txt == "404":
            continue
        rows = parse_rows(txt)
        if rows:
            m = pd.concat([m, pd.DataFrame(rows)], ignore_index=True)
            added.append(str(d))
            print(f"[indices] added {d} ({len(rows)} indices)")
    if added:
        m = m.drop_duplicates(subset=["Date", "Index"]).sort_values(["Index", "Date"])
        keep = sorted(m["Date"].unique())[-KEEP_DATES:]
        m = m[m["Date"].isin(keep)]
        m.to_csv(F, index=False)
    print(f"[indices] master: {m['Date'].nunique()} dates, latest {m['Date'].max().date()}")
    return added


if __name__ == "__main__":
    update_indices()
