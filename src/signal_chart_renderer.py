"""Render compact, email-safe candlestick charts for index sweep signals."""
from __future__ import annotations
import base64, io
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

COLORS={"bg":"#030712","panel":"#0B1120","grid":"#1E293B","text":"#CBD5E1","up":"#10B981","down":"#EF4444","level":"#F59E0B","entry":"#38BDF8","target":"#A78BFA"}


def _clean(df):
    if df is None or df.empty:return pd.DataFrame()
    x=df.copy()
    if isinstance(x.columns,pd.MultiIndex):x.columns=x.columns.get_level_values(0)
    return x.dropna(subset=["Open","High","Low","Close"]).sort_index()


def _fetch(ticker,kind):
    if kind=="weekly":
        d=_clean(yf.download(ticker,period="2y",interval="1d",progress=False,timeout=8))
        if d.empty:return d
        return d.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna().tail(32)
    if kind=="mtf":return _clean(yf.download(ticker,period="10d",interval="15m",progress=False,timeout=8)).tail(130)
    return _clean(yf.download(ticker,period="6mo",interval="1d",progress=False,timeout=8)).tail(55)


def render_signal_chart(signal,kind="daily"):
    """Return PNG as data URI; empty string when market data is unavailable."""
    ticker=signal.get("ticker")
    if not ticker:return ""
    try:df=_fetch(ticker,kind)
    except Exception:return ""
    if len(df)<5:return ""
    # Keep MTF readable in email.
    if kind=="mtf":df=df.tail(80)
    fig,ax=plt.subplots(figsize=(10,3.8),dpi=120)
    fig.patch.set_facecolor(COLORS["bg"]);ax.set_facecolor(COLORS["panel"])
    width=.62
    for i,(_,r) in enumerate(df.iterrows()):
        o,h,l,c=map(float,[r.Open,r.High,r.Low,r.Close]);col=COLORS["up"] if c>=o else COLORS["down"]
        ax.vlines(i,l,h,color=col,linewidth=.8,alpha=.9)
        bottom=min(o,c);height=max(abs(c-o),max(abs(c)*.0002,1e-8))
        ax.add_patch(Rectangle((i-width/2,bottom),width,height,facecolor=col,edgecolor=col,linewidth=.5))
    lines=[]
    if kind=="daily":
        lines=[("Swept",signal.get("swept_level"),COLORS["level"]),("Invalidation",signal.get("day_low"),COLORS["down"])]
    elif kind=="weekly":
        lines=[("Weekly pool",signal.get("swept_level"),COLORS["level"]),("SL",signal.get("stop_loss_level"),COLORS["down"])]
    else:
        lines=[("PWL",signal.get("pwl"),COLORS["level"]),("Entry/MSS",signal.get("entry"),COLORS["entry"]),
               ("SL",signal.get("stoploss"),COLORS["down"]),("T1",signal.get("target_1"),COLORS["up"]),("T2/PWH",signal.get("target_2"),COLORS["target"])]
    for label,val,col in lines:
        if val is None:continue
        try:v=float(val)
        except:continue
        ax.axhline(v,color=col,linewidth=1,linestyle="--",alpha=.9)
        ax.text(len(df)-.5,v,f" {label} {v:,.2f}",color=col,fontsize=7,va="center",ha="left",
                bbox=dict(facecolor=COLORS["bg"],edgecolor="none",alpha=.75,pad=1))
    title=f"{signal.get('name','Index')} • {kind.upper()} SIGNAL CHART • {ticker}"
    ax.set_title(title,color="#F8FAFC",fontsize=10,fontweight="bold",loc="left",pad=8)
    ax.grid(True,color=COLORS["grid"],alpha=.45,linewidth=.5);ax.tick_params(colors=COLORS["text"],labelsize=7)
    for s in ax.spines.values():s.set_color(COLORS["grid"])
    n=len(df);step=max(1,n//6);ticks=list(range(0,n,step));ax.set_xticks(ticks)
    labels=[]
    for i in ticks:
        ts=pd.Timestamp(df.index[i]);labels.append(ts.strftime("%d %b\n%H:%M") if kind=="mtf" else ts.strftime("%d %b"))
    ax.set_xticklabels(labels);ax.set_xlim(-1,n+11)
    fig.tight_layout(pad=1)
    buf=io.BytesIO();fig.savefig(buf,format="png",facecolor=fig.get_facecolor(),bbox_inches="tight");plt.close(fig)
    return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode("ascii")


def chart_html(signal,kind):
    uri=render_signal_chart(signal,kind)
    if not uri:return '<div style="color:#64748B;font-size:11px;margin-top:8px">Chart data temporarily unavailable.</div>'
    return f'<img src="{uri}" alt="{signal.get("name","Index")} {kind} signal chart" style="width:100%;max-width:980px;height:auto;border-radius:8px;border:1px solid #1E293B;margin-top:10px;display:block">'
