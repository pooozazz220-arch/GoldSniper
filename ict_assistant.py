#!/usr/bin/env python3
# Gold Sniper ICT-style market analyst. Analysis only; no orders are placed.
# Safe default: Telegram is OFF unless ENABLE_TELEGRAM=1.
import os, sys, requests, pandas as pd

API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "0") == "1"
SYMBOL = os.getenv("SYMBOL", "XAU/USD")
API = "https://api.twelvedata.com/time_series"

def candles(interval, size=500):
    if not API_KEY:
        raise RuntimeError("TWELVEDATA_API_KEY is missing")
    r = requests.get(API, params={"symbol": SYMBOL, "interval": interval,
        "outputsize": size, "apikey": API_KEY, "format": "JSON", "order": "ASC"},
        timeout=25)
    r.raise_for_status()
    j = r.json()
    if "values" not in j:
        raise RuntimeError("Twelve Data: " + str(j.get("message", j)))
    d = pd.DataFrame(j["values"])
    d["datetime"] = pd.to_datetime(d["datetime"], utc=True, errors="coerce")
    for c in ["open", "high", "low", "close"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["datetime", "open", "high", "low", "close"])
    return d.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

def analyze(df, minutes):
    d = df.copy()
    d["ema20"] = d.close.ewm(span=20, adjust=False).mean()
    d["ema50"] = d.close.ewm(span=50, adjust=False).mean()
    d["ema200"] = d.close.ewm(span=200, adjust=False).mean()
    pc = d.close.shift()
    tr = pd.concat([d.high-d.low, (d.high-pc).abs(), (d.low-pc).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    # Reference levels use only earlier candles, avoiding future-data leakage.
    d["prior_high"] = d.high.shift(1).rolling(20).max()
    d["prior_low"] = d.low.shift(1).rolling(20).min()
    # Three-candle FVG candidates, known only after the third candle closes.
    d["bull_fvg"] = d.low > d.high.shift(2)
    d["bear_fvg"] = d.high < d.low.shift(2)
    cutoff = pd.Timestamp.now(tz="UTC").floor(f"{minutes}min")
    d = d[(d.datetime < cutoff)].dropna(subset=["ema200", "atr14", "prior_high", "prior_low"])
    if len(d) < 3:
        raise RuntimeError("Not enough closed candles")
    x, prev = d.iloc[-1], d.iloc[-2]
    sweep_low = x.low < x.prior_low and x.close > x.prior_low
    sweep_high = x.high > x.prior_high and x.close < x.prior_high
    bull_break = x.close > prev.prior_high
    bear_break = x.close < prev.prior_low
    bull_fvg, bear_fvg = bool(x.bull_fvg), bool(x.bear_fvg)
    uptrend = x.close > x.ema50 > x.ema200
    downtrend = x.close < x.ema50 < x.ema200
    trend = "صعودی" if uptrend else "نزولی" if downtrend else "مختلط/خنثی"
    bull = sum([bool(sweep_low), bool(bull_break), bull_fvg, bool(x.close > x.ema20)])
    bear = sum([bool(sweep_high), bool(bear_break), bear_fvg, bool(x.close < x.ema20)])
    bias = ("سناریوی صعودی؛ ورود هنوز تأیید نشده" if bull >= 3 and bull > bear else
            "سناریوی نزولی؛ ورود هنوز تأیید نشده" if bear >= 3 and bear > bull else
            "بدون سیگنال؛ شواهد کافی نیست")
    return dict(time=x.datetime.strftime("%Y-%m-%d %H:%M UTC"), close=x.close,
        ema20=x.ema20, ema50=x.ema50, ema200=x.ema200, atr=x.atr14,
        prior_high=x.prior_high, prior_low=x.prior_low, trend=trend, bias=bias,
        sweep_low=bool(sweep_low), sweep_high=bool(sweep_high),
        bull_fvg=bull_fvg, bear_fvg=bear_fvg, bull_break=bool(bull_break),
        bear_break=bool(bear_break))

def report(m15, h1):
    f = lambda x: f"{x:.2f}"
    yn = lambda x: "بله" if x else "خیر"
    return "\n".join([
        f"📊 تحلیل ICT-style {SYMBOL} — گزارش پژوهشی، بدون سفارش خودکار",
        f"M15 کندل بسته‌شده: {m15['time']} | Close: {f(m15['close'])}",
        f"روند M15: {m15['trend']} | جمع‌بندی: {m15['bias']}",
        f"EMA20/50/200: {f(m15['ema20'])} / {f(m15['ema50'])} / {f(m15['ema200'])}",
        f"Liquidity sweep پایین/بالا: {yn(m15['sweep_low'])}/{yn(m15['sweep_high'])}",
        f"Bull/Bear FVG: {yn(m15['bull_fvg'])}/{yn(m15['bear_fvg'])}",
        f"شکست محدوده صعودی/نزولی: {yn(m15['bull_break'])}/{yn(m15['bear_break'])}",
        f"محدوده ۲۰ کندل قبلی: {f(m15['prior_low'])} تا {f(m15['prior_high'])} | ATR14: {f(m15['atr'])}",
        "",
        f"H1 کندل بسته‌شده: {h1['time']} | روند: {h1['trend']} | جمع‌بندی: {h1['bias']}",
        f"قیمت H1: {f(h1['close'])}",
        "",
        "توجه: این غربال‌گر ساده با مفاهیم مشابه ICT است، نه اجرای کامل روش ICT.",
        "FVG یا sweep به‌تنهایی ورود نیست. حد ضرر را پشت نقطه ابطال بگذار و ریسک را محدود کن.",
        "قیمت ممکن است با کارگزار MT5 فرق کند. هیچ سودی تضمین نمی‌شود."
    ])

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("BOT_TOKEN/CHAT_ID missing")
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}, timeout=20)
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError("Telegram rejected the message")

def main():
    m15 = analyze(candles("15min"), 15)
    h1 = analyze(candles("1h"), 60)
    msg = report(m15, h1)
    print(msg)
    if ENABLE_TELEGRAM:
        send_telegram(msg)
        print("\nTelegram report sent.")
    else:
        print("\nTelegram disabled: report only, no message sent.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
