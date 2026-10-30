import os, sys, requests, pandas as pd
from datetime import datetime, timedelta, timezone

# ===================== کلیدهای امنیتی =====================
MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "1") == "1"

# ===================== تنظیمات API =====================
TICKER = "XAU/USD"  # دقیقاً طبق مستندات سایت
BASE_URL = "https://api.massive.com"

def get_historical_candles(minutes=15, limit=500):
    """
    دریافت کندل‌های تاریخی (OHLC) 
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=5)
    
    # استفاده از مسیر استاندارد aggregatess
    url = f"{BASE_URL}/v2/aggs/ticker/{TICKER}/range/{minutes}/minute/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
    params = {
        "apiKey": MASSIVE_API_KEY,
        "adjusted": "true",
        "sort": "asc",
        "limit": limit
    }
    
    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        json_data = r.json()
        
        if "results" not in json_data:
            print(f"Massive API Error: {json_data}")
            return pd.DataFrame()
            
        df = pd.DataFrame(json_data["results"])
        df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 't': 'timestamp'})
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        return df.sort_values('datetime').reset_index(drop=True)
    except Exception as e:
        print(f"Error fetching historical candles: {e}")
        return pd.DataFrame()

def get_latest_price():
    """
    دریافت قیمت لحظه‌ای (Snapshot) دقیقاً طبق عکسی که فرستادی
    """
    url = f"{BASE_URL}/v2/snapshot/locale/global/markets/forex/tickers/{TICKER}"
    params = {"apiKey": MASSIVE_API_KEY}
    
    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        # استخراج قیمت از ساختار دیتای Massive
        if "ticker" in data and "lastQuote" in data["ticker"]:
            return float(data["ticker"]["lastQuote"]["askPrice"])
        return None
    except Exception as e:
        print(f"Error fetching snapshot: {e}")
        return None

def analyze_ict(df, minutes=15):
    if df.empty or len(df) < 200:
        return None

    d = df.copy()
    d["ema20"] = d.close.ewm(span=20, adjust=False).mean()
    d["ema50"] = d.close.ewm(span=50, adjust=False).mean()
    d["ema200"] = d.close.ewm(span=200, adjust=False).mean()
    
    pc = d.close.shift()
    tr = pd.concat([d.high-d.low, (d.high-pc).abs(), (d.low-pc).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()
    
    d["bull_fvg"] = d.low > d.high.shift(2)
    d["bear_fvg"] = d.high < d.low.shift(2)
    
    x = d.iloc[-1] 
    
    uptrend = x.close > x.ema50 > x.ema200
    downtrend = x.close < x.ema50 < x.ema200
    trend = "صعودی" if uptrend else "نزولی" if downtrend else "مختلط/خنثی"
    
    bull = sum([bool(x.bull_fvg), bool(x.close > x.ema20)])
    bear = sum([bool(x.bear_fvg), bool(x.close < x.ema20)])
    
    bias = ("سناریوی صعودی؛ ورود هنوز تأیید نشده" if bull >= 2 and bull > bear else
            "سناریوی نزولی؛ ورود هنوز تأیید نشده" if bear >= 2 and bear > bull else
            "بدون سیگنال؛ شواهد کافی نیست")
            
    return {
        "time": x.datetime.strftime("%Y-%m-%d %H:%M UTC"),
        "close": x.close,
        "trend": trend,
        "bias": bias,
        "atr": x.atr14
    }

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("BOT_TOKEN/CHAT_ID missing")
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}, timeout=20)
    r.raise_for_status()

def main():
    print("Fetching data from Massive API...")
    
    live_price = get_latest_price()
    if live_price:
        print(f"Live Price: {live_price}")
    
    df_m15 = get_historical_candles(minutes=15)
    df_h1 = get_historical_candles(minutes=60)
    
    m15_res = analyze_ict(df_m15, 15)
    h1_res = analyze_ict(df_h1, 60)
    
    if not m15_res or not h1_res:
        print("Not enough data for analysis.")
        return

    report = (
        f"📊 تحلیل ICT-style {TICKER} — گزارش پژوهشی\n\n"
        f"💲 قیمت لحظه‌ای: {live_price if live_price else 'نامشخص'}\n"
        f"M15 کندل: {m15_res['time']} | Close: {m15_res['close']:.2f}\n"
        f"روند M15: {m15_res['trend']} | جمع‌بندی: {m15_res['bias']}\n"
        f"ATR14: {m15_res['atr']:.2f}\n\n"
        f"H1 روند: {h1_res['trend']}\n\n"
        f"⚠️ قیمت ممکن است با کارگزار MT5 فرق کند."
    )
    
    print(report)
    
    if ENABLE_TELEGRAM:
        send_telegram(report)
        print("Telegram sent.")

if __name__ == "__main__":
    main()
