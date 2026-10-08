#!/usr/bin/env python3
"""emailer.py — Daily report ko Gmail par bhejne wala module (GitHub Actions se).

Secrets (GitHub repo -> Settings -> Secrets and variables -> Actions):
  GMAIL_USER         = tumhara gmail address  (e.g. abhay@gmail.com)
  GMAIL_APP_PASSWORD = Gmail App Password (16 char, spaces hata ke)
  MAIL_TO            = (optional) kis par bhejna hai; default = GMAIL_USER

Design goals: email-client-safe (sirf inline CSS + tables), mobile friendly (<=640px),
charts CID-inline attached. Agar secrets nahi mile ya Gmail reject kare to skip karo +
GitHub Actions mein ::warning::/::error:: annotation (run kabhi fail nahi, par dikhega zaroor).
"""
from __future__ import annotations
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path

# ---------- palette ----------
NAVY = "#0e1726"
NAVY2 = "#15223a"
GOLD = "#e8b547"
INK = "#1f2937"
MUT = "#6b7280"
BG = "#eef1f6"
CARD = "#ffffff"
LINE = "#e5e9f0"

KEY_THEME = {
    "STRONG": ("#0b7a3e", "#0f9d53", "STRONG BUY", "🟢🟢"),
    "MEDIUM": ("#1b873f", "#2aa355", "MEDIUM BUY", "🟢"),
    "WEAK":   ("#b58105", "#d19a08", "WEAK / CHHOTA", "🟡"),
    "WAIT":   ("#4b5563", "#6b7280", "WAIT — KOI SIGNAL NAHI", "⚪"),
    "NO":     ("#b42318", "#d92d20", "NO ENTRY — KHATRA", "🔴"),
}
GRADE_CLR = {"A+": ("#e7f6ec", "#0b7a3e"), "B": ("#fdf3dc", "#9a6c00"), "C": ("#eef1f6", "#6b7280")}
STATUS_CLR = {"UPTREND": ("#e7f6ec", "#0b7a3e"), "WATCH": ("#fdf3dc", "#9a6c00"),
              "KAMZOR": ("#fef0e6", "#b54708"), "FAIL": ("#fdecea", "#b42318")}


def _chip(txt, bg, fg):
    return (f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
            f'background:{bg};color:{fg};font-size:12px;font-weight:700;'
            f'font-family:Arial,Helvetica,sans-serif;white-space:nowrap;">{txt}</span>')


def _grade_chip(g):
    bg, fg = GRADE_CLR.get(str(g), GRADE_CLR["C"])
    return _chip(("🟢 " if g == "A+" else "🟡 " if g == "B" else "⚪ ") + str(g), bg, fg)


def _status_chip(s):
    s = str(s)
    for k, (bg, fg) in STATUS_CLR.items():
        if k in s:
            return _chip(s, bg, fg)
    return _chip(s, "#eef1f6", MUT)


def _sec_title(emoji, title, sub=""):
    subh = (f'<div style="font-size:12px;color:{MUT};padding-top:2px;">{sub}</div>' if sub else "")
    return f"""
    <tr><td style="padding:26px 28px 10px 28px;">
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:800;
                  color:{INK};letter-spacing:.2px;">{emoji}&nbsp; {title}</div>{subh}
      <div style="height:3px;width:44px;background:{GOLD};border-radius:2px;margin-top:8px;"></div>
    </td></tr>"""


def _tbl_open(headers, widths=None):
    ths = ""
    for i, h in enumerate(headers):
        w = f' width="{widths[i]}"' if widths else ""
        ths += (f'<th{w} style="text-align:left;padding:9px 10px;background:{NAVY};color:#cbd5e1;'
                f'font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:.6px;'
                f'text-transform:uppercase;">{h}</th>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;border:1px solid {LINE};border-radius:8px;">'
            f"<tr>{ths}</tr>")


def _td(x, extra=""):
    return (f'<td style="padding:9px 10px;border-top:1px solid {LINE};'
            f'font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{INK};{extra}">{x}</td>')


def _horizon_block(ctx):
    hz = ctx.get("horizon") or {}
    if not hz:
        return ""
    cell = lambda title, body, sub, dark: f"""
      <td width="20%" valign="top" style="padding:5px;">
        <div style="background:{'#f8fafc' if not dark else '#eef7f0'};border:1px solid {LINE};
                    border-radius:10px;padding:12px 10px;text-align:center;">
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:10.5px;letter-spacing:1px;
                      color:{MUT};font-weight:800;text-transform:uppercase;">{title}</div>
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;
                      color:{INK};padding:7px 0 3px 0;">{body}</div>
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:10.5px;color:{MUT};
                      line-height:1.45;">{sub}</div>
        </div>
      </td>"""
    sec = _sec_title("🔭", "AAGE KA NAZARIYA", "15-saal backtest: is signal ke baad kya hota aaya hai")
    # ⚡ fast-pulse (test-pass short-term flags) — fire hone par card badal jata hai
    p1d, pd4, pd15, p1m = hz.get("p1d", ""), hz.get("pd4", ""), hz.get("pd15", ""), hz.get("p1m", "")
    kal_cell = (cell("Kal", "⚡", f"{p1d}<br/>halka bounce jhukav (12/14 saal)", True)
                if p1d else cell("Kal", "🚫", "koi edge nahi<br/>(coin-flip — tested)", False))
    d4_cell = (cell("1-4 Din", "⚡", f"{pd4}<br/>halka jhukav", True)
               if pd4 else cell("1-4 Din", f"{hz.get('d4w','—')}% ⬆",
                                f"avg {hz.get('d4a',0):+.1f}%<br/>baseline jitna — edge nahi", False))
    if pd15:
        body15, sub15, dark15 = ("🔻" if hz.get("sd15") else "⚡"), f"{pd15}", True
    elif hz.get("sd15"):
        body15, sub15, dark15 = "🔻", "15-din KAMZORI signal<br/>(dono test-periods verified)", True
    else:
        body15, sub15, dark15 = f"{hz.get('d15w','—')}% ⬆", f"avg {hz.get('d15a',0):+.1f}%<br/>signal jaagna shuru", False
    d15_cell = cell("15 Din", body15, sub15, dark15)
    m1_sub = f"avg {hz.get('m1a',0):+.1f}%<br/>halka edge" + (f"<br/><b>{p1m}</b>" if p1m else "")
    return f"""{sec}
  <tr><td style="padding:4px 22px 6px 22px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      {kal_cell}
      {d4_cell}
      {d15_cell}
      {cell("1 Mahina", f"{hz.get('m1w','—')}% ⬆", m1_sub, True)}
      {cell("2 Mahine", f"{hz.get('m2w','—')}% ⬆", f"avg {hz.get('m2a',0):+.1f}%<br/><b>ASLI EDGE yahi hai</b>", True)}
    </tr></table>
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11.5px;color:{MUT};padding-top:8px;
                line-height:1.5;">💡 Result ka asli test 1-2 mahine baad — beech ka shor ignore karo,
                sirf -10% stop-loss follow karo.</div>
  </td></tr>"""


def _scorecard_block(ctx):
    sc = ctx.get("scorecard") or {}
    if not sc or not sc.get("n"):
        return ""
    big = lambda label, val: f"""
      <td width="33%" valign="top" style="padding:6px;">
        <div style="background:#eef7f0;border:1px solid {LINE};border-radius:10px;
                    padding:14px 10px;text-align:center;">
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:26px;font-weight:800;
                      color:{INK};">{val}</div>
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:10.5px;letter-spacing:1px;
                      color:{MUT};font-weight:800;text-transform:uppercase;padding-top:4px;">{label}</div>
        </div>
      </td>"""
    chips = ""
    for d, b, r40, ok in sc.get("last", []):
        col = "#1d7a46" if ok else "#b3402e"
        mark = "✅" if ok else "❌"
        chips += (f'<span style="display:inline-block;background:#f8fafc;border:1px solid {LINE};'
                  f'border-radius:14px;padding:4px 10px;margin:3px 4px 3px 0;font-family:Arial,'
                  f'Helvetica,sans-serif;font-size:11px;color:{INK};">{d} · {b} · '
                  f'<b style="color:{col};">{r40} {mark}</b></span>')
    sec = _sec_title("📒", "SYSTEM KA APNA REPORT CARD", "pichhle 12 mahine ke signals — khud ka hisaab, roz update")
    return f"""{sec}
  <tr><td style="padding:4px 22px 2px 22px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      {big("Signals (12 mah.)", sc.get("n", "—"))}
      {big("20-din sahi", f"{sc.get('hit20', '—')}%")}
      {big("40-din sahi", f"{sc.get('hit40', '—')}%")}
    </tr></table>
    <div style="padding:6px 6px 2px 6px;">{chips}</div>
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUT};padding:4px 6px 0 6px;
                line-height:1.5;">🪞 System apne purane signals se bhaag nahi sakta — accuracy giri to yahin dikhegi.</div>
  </td></tr>"""


def _alert_banner(ctx):
    a = ctx.get("alert") or ""
    if not a:
        return ""
    return f"""
  <tr><td style="padding:14px 22px 0 22px;">
    <div style="background:#7a1d1d;border-radius:10px;padding:14px 16px;text-align:center;">
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;letter-spacing:1.5px;
                  color:#ffd9d9;font-weight:800;">&#128680; SIGNAL BADLA AAJ</div>
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;
                  color:#ffffff;padding-top:5px;">{a}</div>
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#ffc9c9;
                  padding-top:4px;">Aaj ka email dhyan se padho &mdash; kal se alag action ho sakta hai.</div>
    </div>
  </td></tr>"""


def _position_block(ctx):
    po = ctx.get("position") or {}
    if not po:
        return ""
    col = "#1d7a46" if po.get("pnl_pos") else "#b3402e"
    sec = _sec_title("\U0001F4CB", "SYSTEM KA SWING TRADE", "virtual trade — entry se exit tak system khud manage karta hai")
    if po.get("status") == "OPEN":
        def cell(t, v, s, dark=False):
            bg = "#eef7f0" if dark else "#f8fafc"
            return f"""
      <td width="25%" style="padding:5px;"><div style="background:{bg};border:1px solid {LINE};border-radius:10px;padding:12px 8px;text-align:center;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:10.5px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;">{t}</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:800;color:{INK};padding-top:5px;">{v}</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};padding-top:2px;">{s}</div></div></td>"""
        pnl_cell = f"""
      <td width="25%" style="padding:5px;"><div style="background:#eef7f0;border:1px solid {LINE};border-radius:10px;padding:12px 8px;text-align:center;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:10.5px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;">P&amp;L abhi</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:800;color:{col};padding-top:5px;">{po.get('pnl')}</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};padding-top:2px;">@ {po.get('now')}</div></div></td>"""
        body = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      {cell("Entry", po.get('entry',''), po.get('entry_date',''))}
      {pnl_cell}
      {cell("Stop-loss", po.get('stop',''), str(po.get('dist','')) + " door")}
      {cell("Hold", str(po.get('days','')) + " din", "target 1-2 mahine")}
    </tr></table>
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11.5px;color:{MUT};padding-top:7px;line-height:1.5;">
      &#127919; Trade chaalu hai &mdash; kuch mat karo. Exit sirf: stop hit YA exit signal (yahi email bata dega).</div>"""
    else:
        body = f"""
    <div style="background:#f8fafc;border:1px solid {LINE};border-radius:10px;padding:14px 16px;">
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:800;color:{INK};">
        Trade BAND hua: {po.get('entry')} ({po.get('entry_date')}) &rarr; {po.get('now')} =
        <span style="color:{col};">{po.get('pnl')}</span></div>
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:11.5px;color:{MUT};padding-top:4px;">
        Wajah: {po.get('reason','')} &middot; Agla STRONG_BUY aane par naya trade khulega.</div>
    </div>"""
    return f"""{sec}
  <tr><td style="padding:4px 22px 6px 22px;">{body}</td></tr>"""


def _bnf_block(ctx):
    b = ctx.get("bnf") or {}
    if not b:
        return ""
    col = "#1d7a46" if b.get("chg_pos") else "#b3402e"
    sec = _sec_title("\U0001F3E6", "BANK NIFTY", "wahi signal, dusra index — 15-saal verified (BANKBEES)")
    sd_note = ""
    if b.get("sd"):
        sd_note = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:11.5px;color:#b3402e;'
                   'font-weight:800;padding-top:6px;">&#128315; STRONG_DOWN: BNF bhi 2 mahine '
                   'flat/negative raha hai &mdash; BANKBEES se bhi door raho.</div>')
    def cell(t, v, dark=False):
        bg = "#eef7f0" if dark else "#f8fafc"
        return f"""
      <td width="25%" style="padding:5px;"><div style="background:{bg};
          border:1px solid {LINE};border-radius:10px;padding:11px 8px;text-align:center;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;
                    text-transform:uppercase;letter-spacing:1px;">{t}</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:800;color:{INK};
                    padding-top:5px;">{v}</div></div></td>"""
    today_cell = f"""
      <td width="25%" style="padding:5px;"><div style="background:#f8fafc;border:1px solid {LINE};
          border-radius:10px;padding:11px 8px;text-align:center;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;
                    text-transform:uppercase;letter-spacing:1px;">BNF aaj</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:800;color:{INK};
                    padding-top:5px;">{b.get('close')} <span style="color:{col};font-size:11px;">{b.get('chg')}</span></div></div></td>"""
    return f"""{sec}
  <tr><td style="padding:4px 22px 6px 22px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      {today_cell}
      {cell("15 din (avg/up)", b.get("d15",""))}
      {cell("1 mahina", b.get("m1",""))}
      {cell("2 mahine", b.get("m2",""), True)}
    </tr></table>
    {sd_note}
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUT};padding-top:6px;line-height:1.5;">
      Participant OI signal poore market ka hai &mdash; BNF par alag se 15y verify kiya (IC +0.157 @40d).</div>
  </td></tr>"""


def _sector_block(ctx):
    sc = ctx.get("sector") or {}
    if not sc or not sc.get("ranks"):
        return ""
    active = sc.get("active")
    sec = _sec_title("\U0001F9ED", "SECTOR ROTATION", "sabse majboot sector — bullish signal ke saath hi lagana (15y tested)")
    if active:
        badge = ('<div style="display:inline-block;background:#1d7a46;color:#ffffff;border-radius:14px;'
                 'padding:5px 14px;font-family:Arial,Helvetica,sans-serif;font-size:11.5px;font-weight:800;'
                 'letter-spacing:1px;">\u2705 ACTIVE \u2014 OI signal bullish, tilt chalu</div>')
        note = ("15y test: bullish signal ke waqt top-2 sector basket baaki market se +0.8\u20131.0pp (40d) aage "
                "(out-of-sample bhi). Sector ke 3-4 bade stocks mein <b>barabar baanto</b> \u2014 "
                "1-2 stock chunne ka edge test mein nahi mila. Stop -10%.")
    else:
        badge = ('<div style="display:inline-block;background:#8a6d1d;color:#ffffff;border-radius:14px;'
                 'padding:5px 14px;font-family:Arial,Helvetica,sans-serif;font-size:11.5px;font-weight:800;'
                 'letter-spacing:1px;">\u23F8 STANDBY \u2014 signal bullish nahi, sirf dekho</div>')
        note = ("Tested sach: sector tilt <b>sirf bullish OI signal ke saath</b> kaam karta hai \u2014 "
                "bina signal out-of-sample NEGATIVE tha. Signal aane par ye ACTIVE ho jayega.")
    chips = ""
    for s, m, tag in sc.get("ranks", []):
        if tag == "top":
            bg, bc, ic = "#eef7f0", "#1d7a46", "\U0001F7E2 "
        elif tag == "bot":
            bg, bc, ic = "#fdf0ee", "#b3402e", "\U0001F534 "
        else:
            bg, bc, ic = "#f8fafc", LINE, ""
        chips += (f'<span style="display:inline-block;background:{bg};border:1px solid {bc};'
                  f'border-radius:14px;padding:5px 11px;margin:3px 4px 3px 0;font-family:Arial,'
                  f'Helvetica,sans-serif;font-size:11.5px;color:{INK};">{ic}<b>{s}</b> {m}</span>')
    stocks = ""
    for s, lst in sc.get("stocks", []):
        stocks += (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:11.5px;color:{INK};'
                   f'padding-top:4px;"><b>{s}:</b> <span style="color:{MUT};">{lst}</span></div>')
    return f"""{sec}
  <tr><td style="padding:4px 22px 6px 22px;">
    {badge}
    <div style="padding:8px 0 2px 0;">{chips}</div>
    {stocks}
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUT};padding-top:7px;line-height:1.5;">{note}</div>
  </td></tr>"""


def _gems_block(ctx):
    gm = ctx.get("gems") or {}
    if not gm:
        return ""
    sec = _sec_title("\U0001F48E", "GEM SCANNER", "25-40% mover ka decoded setup — mahine mein ~1 baar (15y tested)")
    if gm.get("n"):
        rows = ""
        for st, sc, px, ds, vs, stp, tgt in gm.get("cands", []):
            rows += f"""
      <tr>
        <td style="padding:8px 10px;font-family:Arial,Helvetica,sans-serif;font-size:12.5px;font-weight:800;color:{INK};border-bottom:1px solid {LINE};">\U0001F48E {st} <span style="color:{MUT};font-weight:400;">({sc})</span></td>
        <td style="padding:8px 10px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{INK};border-bottom:1px solid {LINE};text-align:right;">{px}</td>
        <td style="padding:8px 10px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#b3402e;border-bottom:1px solid {LINE};text-align:right;">{ds}</td>
        <td style="padding:8px 10px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{INK};border-bottom:1px solid {LINE};text-align:right;">{vs}</td>
        <td style="padding:8px 10px;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;color:#b3402e;border-bottom:1px solid {LINE};text-align:right;">{stp}</td>
        <td style="padding:8px 10px;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;color:#1d7a46;border-bottom:1px solid {LINE};text-align:right;">{tgt}</td>
      </tr>"""
        body = f"""
    <div style="display:inline-block;background:#1d7a46;color:#ffffff;border-radius:14px;padding:5px 14px;
                font-family:Arial,Helvetica,sans-serif;font-size:11.5px;font-weight:800;letter-spacing:1px;">
      \U0001F48E SETUP FIRE \u2014 {gm.get('n')} stock(s)</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">
      <tr>
        <td style="padding:6px 10px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;">Stock</td>
        <td style="padding:6px 10px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;text-align:right;">Price</td>
        <td style="padding:6px 10px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;text-align:right;">52w se</td>
        <td style="padding:6px 10px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;text-align:right;">Vol</td>
        <td style="padding:6px 10px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;text-align:right;">Stop</td>
        <td style="padding:6px 10px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:{MUT};font-weight:800;text-transform:uppercase;letter-spacing:1px;text-align:right;">Target</td>
      </tr>{rows}
    </table>
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUT};padding-top:7px;line-height:1.5;">
      Entry agle din \u00b7 max hold 3 mahine \u00b7 ek gem mein portfolio ka 5-10% se zyada NAHI.
      15y: OOS win 67%, 47% baar +25% target hit. Bear saal mein ye bhi haarta hai \u2014 deploy % Master Signal se.</div>"""
    else:
        wtxt = ""
        if gm.get("watch"):
            wtxt = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:11.5px;color:' + INK +
                    ';padding-top:6px;"><b>Banne ke kareeb (volume ka intezaar):</b> ' +
                    ", ".join(gm["watch"]) + "</div>")
        body = f"""
    <div style="background:#f8fafc;border:1px solid {LINE};border-radius:10px;padding:13px 16px;">
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:12.5px;color:{INK};">
        Aaj koi gem setup nahi \u2014 <b>ye normal hai</b> (mahine mein ~1 aata hai; isi selectivity mein edge hai).</div>
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUT};padding-top:5px;line-height:1.5;">
        Pattern: 52w-high se 40%+ gira + EMA50 reclaim + volume 1.5x \u2014 fire hote hi yahan aur Telegram par dikhega.</div>
      {wtxt}
    </div>"""
    track = gm.get("track") or []
    if track:
        chips = ""
        for d, s, st in track:
            col = "#1d7a46" if st.startswith("✅") else ("#b3402e" if st.startswith("❌") else MUT)
            chips += (f'<span style="display:inline-block;background:#f8fafc;border:1px solid {LINE};'
                      f'border-radius:14px;padding:4px 10px;margin:3px 4px 3px 0;font-family:Arial,'
                      f'Helvetica,sans-serif;font-size:11px;color:{INK};">{d} <b>{s}</b> '
                      f'<b style="color:{col};">{st}</b></span>')
        tsum = gm.get("tsum") or ""
        body += (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:10.5px;color:{MUT};'
                 f'font-weight:800;text-transform:uppercase;letter-spacing:1px;padding-top:10px;">'
                 f'📒 Pichle gems ka hisaab {("(" + tsum + ")") if tsum else ""}</div>'
                 f'<div style="padding-top:3px;">{chips}</div>')
    return f"""{sec}
  <tr><td style="padding:4px 22px 6px 22px;">{body}</td></tr>"""


def _stocks_block(ctx):
    rows = ctx.get("stocks") or []
    if not rows:
        return ""
    sec = _sec_title("\U0001F3C6", "STRONGEST STOCKS (NIFTY 50)", "A+ = EMA50 upar + RS top-10% — 15y tested edge")
    chips = ""
    for row in rows[:6]:
        if not isinstance(row, (list, tuple)) or len(row) < 4:
            continue  # malformed row skip — email kabhi na toote
        name, rs, r1m, price = row[:4]
        up = not str(r1m).startswith("-")
        ccol = "#1d7a46" if up else "#b3402e"
        chips += (f'<span style="display:inline-block;background:#eef7f0;border:1px solid {LINE};'
                  f'border-radius:14px;padding:6px 12px;margin:3px 5px 3px 0;font-family:Arial,'
                  f'Helvetica,sans-serif;font-size:12px;color:{INK};"><b>{name}</b> &middot; RS {rs} '
                  f'&middot; <b style="color:{ccol};">{r1m}</b> (1m) &middot; {price}</span>')
    return f"""{sec}
  <tr><td style="padding:4px 22px 6px 22px;">
    <div style="padding:2px 0;">{chips}</div>
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUT};padding-top:6px;line-height:1.5;">
      &#128161; Ye "KYA kharidna" ka shortlist hai &mdash; KAB/KITNA Master Signal batayega.
      15y test: basket ne baseline ko +1.0pp @40d / +1.7pp @60d se beat kiya (OOS +0.5/+1.1pp).
      Horizon 1-3 mahine, stop -10%.</div>
  </td></tr>"""


def _safe(fn, ctx):
    """Koi ek block gire to pura email na gire — fail-safe render."""
    try:
        return fn(ctx)
    except Exception as e:
        print(f"[email] block {getattr(fn, '__name__', '?')} fail (skip): {e}")
        return ""


def build_html(ctx: dict) -> str:
    """ctx: p, key, S, D, pct, lakh, trend, sweep_setups, weekly_setups, drows, wrows,
    repo_url (optional)."""
    # Fail-safe defaults: koi core key missing ho to bhi email bane (crash nahi)
    p = ctx.get("p") or {}
    p.setdefault("bucket", "WAIT"); p.setdefault("score_v2", 0.0)
    p.setdefault("bottom_signal_B3", False); p.setdefault("top_warning_T4", False)
    p.setdefault("data_date", "—"); p.setdefault("nifty_close", 0)
    ctx["p"] = p
    key = ctx.get("key", "WAIT")
    S = ctx.get("S") or {}
    S.setdefault("kya_karna", ["Data aane ka intezaar karo"])
    S.setdefault("one_liner", "Data abhi incomplete hai — koi action nahi.")
    S.setdefault("accuracy", "—")
    pct = ctx.get("pct", 0)
    lakh = ctx.get("lakh", 0)
    if not isinstance(lakh, (int, float)):
        lakh = 0
    D = ctx.get("D") or ["data incomplete", "wait karo"]
    if not isinstance(D, (list, tuple)) or len(D) < 2:
        D = ["data incomplete", "wait karo"]
    trend = ctx.get("trend", "—")
    dark, lite, label, emoji = KEY_THEME.get(key, KEY_THEME["WAIT"])

    steps = "".join(
        f'<tr><td style="padding:7px 0 7px 0;vertical-align:top;width:30px;">'
        f'<div style="width:22px;height:22px;border-radius:50%;background:{NAVY};color:{GOLD};'
        f'font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;text-align:center;'
        f'line-height:22px;">{i+1}</div></td>'
        f'<td style="padding:7px 0 7px 10px;font-family:Arial,Helvetica,sans-serif;font-size:13.5px;'
        f'color:{INK};line-height:1.55;">{s}</td></tr>'
        for i, s in enumerate(S["kya_karna"]))

    # deployment bar
    filled = max(4, min(100, pct))
    bar = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="background:#e6eaf1;border-radius:999px;height:16px;overflow:hidden;">
        <table role="presentation" cellpadding="0" cellspacing="0" width="{filled}%" style="height:16px;"><tr>
          <td style="background:{dark};border-radius:999px;height:16px;font-size:1px;">&nbsp;</td>
        </tr></table>
      </td></tr></table>"""

    # market status rows
    b3 = p["bottom_signal_B3"]
    t4 = p["top_warning_T4"]
    b3_on = "ACTIVE" in str(b3)
    t4_on = "ACTIVE" in str(t4)
    mrows = [
        ("Market trend (200-DMA)", f"<b>{trend}</b>",
         "healthy zone" if trend.startswith("UPAR") else "kamzor zone — sambhal ke"),
        ("Bade khiladi (FII/Pro)", f"<b>{str(p['bucket']).replace('_', ' ')}</b> &nbsp;"
         + _chip(f"score {p['score_v2']:+.2f}", "#eef1f6", INK),
         "+2.5↑ = zor se kharid | −2.5↓ = zor se bech"),
        ("🟢 Bottom signal (B3)",
         _chip(b3, *( ("#e7f6ec", "#0b7a3e") if b3_on else ("#eef1f6", MUT) )),
         "10 mein 8 baar sahi" if b3_on else "abhi nahi"),
        ("🔴 Top warning (T4)",
         _chip(t4, *( ("#fdecea", "#b42318") if t4_on else ("#eef1f6", MUT) )),
         "profit bachao" if t4_on else "abhi nahi"),
    ]
    mtbl = _tbl_open(["Cheez", "Status", "Matlab"], ["30%", "40%", "30%"])
    for a, b, c in mrows:
        mtbl += f"<tr>{_td(a, 'color:'+MUT+';')}{_td(b)}{_td(c, 'color:'+MUT+';font-size:12px;')}</tr>"
    mtbl += "</table>"

    # sweep tables
    def sweep_tbl(setups, weekly=False):
        if not setups:
            return (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{MUT};'
                    f'padding:4px 0;">Aaj koi {"weekly " if weekly else ""}setup nahi bana — '
                    f'koi baat nahi, roz nahi bante.</div>')
        t = _tbl_open(["Index", "Grade", "RS", "Level sweep", "Stop"], ["34%", "14%", "12%", "22%", "18%"])
        for s in setups[:6]:
            rs = s.get("RS_pct")
            rs_txt = f"{rs:.0f}" if rs == rs else "—"
            lvl = s.get("Swept_Level", s.get("Level", "—"))
            stop = s.get("Stop_Loss", s.get("Sweep_Low", "—"))
            lvl = f"{lvl:,.0f}" if isinstance(lvl, (int, float)) else lvl
            stop = f"{stop:,.0f}" if isinstance(stop, (int, float)) else stop
            t += ("<tr>" + _td(f"<b>{s['Index']}</b>") + _td(_grade_chip(s.get("Grade", "—")))
                  + _td(rs_txt) + _td(lvl) + _td(stop) + "</tr>")
        t += "</table>"
        if len(setups) > 6:
            t += (f'<div style="font-size:11px;color:{MUT};font-family:Arial;padding-top:5px;">'
                  f"...aur {len(setups)-6} setups (GitHub report mein)</div>")
        return t

    # report card
    def track_tbl(rows, weekly=False):
        if not rows:
            return (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{MUT};">'
                    f"Tracking mein abhi kuch nahi.</div>")
        cnt = {"UPTREND": 0, "WATCH": 0, "KAMZOR": 0, "FAIL": 0}
        for r in rows:
            for k in cnt:
                if k in str(r["Status"]):
                    cnt[k] += 1
        score = (f'{_chip("✅ "+str(cnt["UPTREND"]), *STATUS_CLR["UPTREND"])} '
                 f'{_chip("🟡 "+str(cnt["WATCH"]), *STATUS_CLR["WATCH"])} '
                 f'{_chip("🟠 "+str(cnt["KAMZOR"]), *STATUS_CLR["KAMZOR"])} '
                 f'{_chip("❌ "+str(cnt["FAIL"]), *STATUS_CLR["FAIL"])}')
        agec = "Weeks_Ago" if weekly else "Days_Ago"
        unit = "hafte" if weekly else "din"
        t = _tbl_open(["Index", "Kab", "% Since", "Status"], ["36%", "18%", "18%", "28%"])
        for r in rows[:6]:
            ret = r["Ret_"]
            rc = "#0b7a3e" if ret >= 0 else "#b42318"
            t += ("<tr>" + _td(f"<b>{r['Index']}</b>")
                  + _td(f"{r[agec]} {unit} pehle", "color:" + MUT + ";")
                  + _td(f'<b style="color:{rc};">{ret:+.1f}%</b>')
                  + _td(_status_chip(r["Status"])) + "</tr>")
        t += "</table>"
        if len(rows) > 6:
            t += (f'<div style="font-size:11px;color:{MUT};font-family:Arial;padding-top:5px;">'
                  f"...aur {len(rows)-6} tracked (GitHub report mein)</div>")
        return f'<div style="padding-bottom:10px;">{score}</div>' + t

    charts_html = ""
    for i, (cap, _) in enumerate(ctx.get("inline_charts", [])):
        charts_html += f"""
        <tr><td style="padding:8px 28px 4px 28px;">
          <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{MUT};
                      padding-bottom:6px;">{cap}</div>
          <img src="cid:chart{i}" width="584" style="width:100%;max-width:584px;border:1px solid {LINE};
               border-radius:8px;display:block;" alt="{cap}"/>
        </td></tr>"""

    repo_url = ctx.get("repo_url", "")
    repo_btn = (f"""<a href="{repo_url}" style="display:inline-block;background:{GOLD};color:{NAVY};
                 font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:800;
                 text-decoration:none;padding:10px 22px;border-radius:8px;">
                 📄 Puri report GitHub par dekho</a>""" if repo_url else "")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width"/></head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
<tr><td align="center" style="padding:24px 10px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0"
       style="max-width:640px;width:100%;background:{CARD};border-radius:14px;overflow:hidden;
              box-shadow:0 2px 12px rgba(15,23,42,.08);">

  <!-- HEADER -->
  <tr><td style="background:{NAVY};background:linear-gradient(135deg,{NAVY} 0%,{NAVY2} 100%);
                 padding:26px 28px 22px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:3px;
                    color:{GOLD};font-weight:800;">SMART MONEY · DAILY INTELLIGENCE</div>
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:26px;color:#ffffff;
                    font-weight:700;padding-top:6px;">Aaj Ka Signal Report</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:12.5px;color:#94a3b8;
                    padding-top:6px;">{p['data_date']} &nbsp;•&nbsp; NSE shaam ke data se
                    &nbsp;•&nbsp; Nifty <b style="color:#e2e8f0;">{p['nifty_close']:,}</b></div>
      </td>
      <td align="right" valign="top" style="font-size:30px;">{emoji}</td>
    </tr></table>
  </td></tr>

  {f'<tr><td style="background:#b42318;padding:12px 28px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#ffffff;font-weight:700;">{ctx["warn"]}</td></tr>' if ctx.get("warn") else ""}
  {_alert_banner(ctx)}
  <!-- HERO SIGNAL -->
  <tr><td style="padding:0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="background:{dark};background:linear-gradient(135deg,{dark},{lite});
                     padding:22px 28px;">
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;letter-spacing:2px;
                    color:rgba(255,255,255,.75);font-weight:700;">ENTRY SIGNAL</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:24px;color:#ffffff;
                    font-weight:800;padding:4px 0 8px 0;">{emoji} {label}</div>
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:13.5px;color:rgba(255,255,255,.95);
                    line-height:1.6;">{S['one_liner']}</div>
      </td></tr>
    </table>
  </td></tr>

  <!-- DEPLOYMENT -->
  {_sec_title("💰", "KITNA PAISA MARKET MEIN", "MASTER SIGNAL deployment level")}
  <tr><td style="padding:4px 28px 6px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="font-family:Arial,Helvetica,sans-serif;font-size:34px;font-weight:800;color:{INK};
                 width:110px;">{pct}%</td>
      <td style="padding-left:6px;">{bar}
        <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{MUT};padding-top:7px;">
          ₹1,00,000 par: <b style="color:{INK};">₹{lakh:,} market</b> + ₹{100000-lakh:,} cash</div>
      </td>
    </tr></table>
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:12.5px;color:{MUT};line-height:1.55;
                padding-top:10px;">Kyun? {D[0]} — isliye {D[1]}.</div>
  </td></tr>

  <!-- GAME PLAN -->
  {_sec_title("✅", "AAJ KA GAME PLAN", "step-by-step — bilkul simple")}
  <tr><td style="padding:2px 28px 6px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{steps}</table>
    <div style="background:#f8fafc;border:1px solid {LINE};border-radius:8px;padding:10px 14px;
                margin-top:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{MUT};">
      📊 <b style="color:{INK};">Track record:</b> {S['accuracy']}</div>
  </td></tr>

  <!-- MARKET STATUS -->
  {_sec_title("📖", "MARKET KA HAAL", "ek nazar mein")}
  <tr><td style="padding:4px 28px 6px 28px;">{mtbl}</td></tr>

  {_safe(_horizon_block, ctx)}

  {_safe(_scorecard_block, ctx)}

  {_safe(_position_block, ctx)}

  {_safe(_bnf_block, ctx)}

  {_safe(_sector_block, ctx)}

  {_safe(_gems_block, ctx)}

  {_safe(_stocks_block, ctx)}

  <!-- DAILY SWEEP -->
  {_sec_title("🧲", "DAILY SWEEP SETUPS", "kal ke liye strongest index watchlist (A+ = sweep + strong index)")}
  <tr><td style="padding:4px 28px 6px 28px;">{sweep_tbl(ctx.get("sweep_setups", []))}</td></tr>

  <!-- WEEKLY SWEEP -->
  {_sec_title("📅", "WEEKLY SWEEP SETUPS", "zyada strong signal — 4-8 hafte ka swing watchlist")}
  <tr><td style="padding:4px 28px 6px 28px;">{sweep_tbl(ctx.get("weekly_setups", []), weekly=True)}</td></tr>

  <!-- REPORT CARD -->
  {_sec_title("📋", "SWEEP REPORT CARD", "pichle setups ka hisaab — jo hai woh dikhega, chhupana kuch nahi")}
  <tr><td style="padding:4px 28px 2px 28px;">
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;color:{INK};
                padding-bottom:8px;">DAILY (pichle 10 din)</div>
    {track_tbl(ctx.get("drows", []))}
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:800;color:{INK};
                padding:16px 0 8px 0;">WEEKLY (pichle 3 hafte)</div>
    {track_tbl(ctx.get("wrows", []), weekly=True)}
  </td></tr>

  <!-- CHARTS -->
  {_sec_title("📈", "AAJ KE TOP CHARTS") if ctx.get("inline_charts") else ""}
  {charts_html}

  <!-- CTA -->
  <tr><td align="center" style="padding:20px 28px 6px 28px;">{repo_btn}</td></tr>

  <!-- RULES -->
  <tr><td style="padding:18px 28px 6px 28px;">
    <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;
                font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#92400e;line-height:1.7;">
      <b>🧒 PAKKE NIYAM:</b> Stop-loss −8% hamesha • Paisa 2-3 kisht mein • Udhaar/EMI ka paisa kabhi
      nahi • System 10 mein 7-8 baar sahi hai, 2-3 baar galat bhi — niyam hi asli bachav hain •
      Confusion ho to NIFTYBEES.</div>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:{NAVY};padding:18px 28px;margin-top:10px;">
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#64748b;line-height:1.7;">
      Ye financial advice nahi hai — 15 saal ke NSE data par bana educational research system hai.<br/>
      ⚙️ Auto-generated by GitHub Actions • {p.get('generated_utc','')} UTC</div>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


def send_email(ctx: dict, out_dir: Path) -> bool:
    """HTML banao, preview save karo, aur (agar secrets hain to) Gmail se bhejo."""
    html = build_html(ctx)
    try:
        # preview browser mein khul sake isliye cid: ko relative chart path se replace karo
        pv = html
        for i, (_, path) in enumerate(ctx.get("inline_charts", [])):
            pv = pv.replace(f"cid:chart{i}", "charts/" + Path(path).name)
        (out_dir / "email_preview.html").write_text(pv)
        print("[email] preview saved -> output/email_preview.html")
    except Exception as e:
        print(f"[email] preview save fail: {e}")

    user = (os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER")
            or os.environ.get("SMTP_USER") or "").strip()
    pwd = (os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("GMAIL_PASS")
           or os.environ.get("EMAIL_PASS") or os.environ.get("SMTP_PASS")
           or os.environ.get("APP_PASSWORD") or "")
    # BUG FIX: secret copy-paste karte waqt trailing space / newline aa jaati hai →
    # Gmail auth fail ho jaata tha aur mail silently nahi jaati thi. Sab whitespace hata do.
    pwd = "".join(pwd.split())
    to = (os.environ.get("MAIL_TO") or "").strip() or user
    to = ",".join(x.strip() for x in to.split(",") if x.strip())

    def _mask(s: str) -> str:
        return (s[:3] + "***" + s[-4:]) if len(s) > 8 else "***"

    if not user or not pwd:
        missing = [n for n, v in (("GMAIL_USER", user), ("GMAIL_APP_PASSWORD", pwd)) if not v]
        print(f"[email] missing secrets: {', '.join(missing)} — email skip")
        print("::warning::Email nahi bhej paya — repo Secrets (Settings → Secrets and variables → "
              "Actions) mein ye add karo: " + ", ".join(missing) + " (optional: MAIL_TO). "
              "GMAIL_USER = tumhara gmail address; GMAIL_APP_PASSWORD = 16-character App Password "
              "(Google Account → Security → 2-Step Verification ON karo → App passwords → naya banao). "
              "Normal Gmail login password nahi chalega.")
        return False
    print(f"[email] config ok: user={_mask(user)} | to={_mask(to)} | app_password_len={len(pwd)}")

    p = ctx["p"]
    _, _, label, emoji = KEY_THEME.get(ctx["key"], KEY_THEME["WAIT"])
    subject = f"{emoji} {label} • {ctx['pct']}% invested • Nifty {p['nifty_close']:,} • {p['data_date']}"
    if ctx.get("alert"):
        subject = "🚨 SIGNAL BADLA • " + str(ctx["alert"])[:70] + " • " + str(p["data_date"])

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = f"Smart Money Report <{user}>"
    msg["To"] = to
    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    plain = (f"{label} | Deploy {ctx['pct']}% | Nifty {p['nifty_close']} | {p['data_date']}\n"
             f"{ctx['S']['one_liner']}\nHTML report ke liye email client mein kholo.")
    alt.attach(MIMEText(plain, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))

    for i, (cap, path) in enumerate(ctx.get("inline_charts", [])):
        try:
            img = MIMEImage(Path(path).read_bytes())
            img.add_header("Content-ID", f"<chart{i}>")
            img.add_header("Content-Disposition", "inline", filename=Path(path).name)
            msg.attach(img)
        except Exception as e:
            print(f"[email] chart attach fail ({path}): {e}")

    def _auth_fail(stage, e):
        print(f"[email] AUTH FAIL ({stage}): {e}")
        print("::error::Gmail login reject ho gaya — GMAIL_USER ya GMAIL_APP_PASSWORD galat hai. "
              "Yaad rakho: App Password = 16-character wala (Google Account → Security → "
              "2-Step Verification ON karo → App passwords → naya banao). Apna normal Gmail "
              "login password nahi chalega. Secret mein extra space/newline nahi honi chahiye "
              "(ab woh automatically hata di jaati hai).")

    try:
        c = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=c, timeout=30) as s:
            s.login(user, pwd)
            s.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
        print(f"[email] sent -> {to}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        _auth_fail("465", e)
        return False
    except Exception as e:
        print(f"[email] send fail (465): {e}")
        # dusri koshish: STARTTLS 587 (kuch networks 465 block karte hain)
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pwd)
                s.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
            print(f"[email] sent via 587 -> {to}")
            return True
        except smtplib.SMTPAuthenticationError as e2:
            _auth_fail("587", e2)
            return False
        except Exception as e2:
            print(f"[email] 587 bhi fail: {e2}")
            print("::error::Email nahi bhej paya — Gmail SMTP (465 + 587) dono par fail. "
                  "Check karo: GMAIL_USER / GMAIL_APP_PASSWORD secrets sahi hain? "
                  f"Error: {e2}")
            return False
