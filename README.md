import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import datetime

# خواندن توکن‌ها از تنظیمات امنیتی
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال: {e}")

def analyze_live_market():
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period="2d", interval="1m")
    
    if df.empty:
        print("بازار بسته است یا داده‌ای دریافت نشد.")
        return

    # محاسبه کندل‌های ۱۵ دقیقه‌ای
    df['Is_Green_M1'] = (df['Close'] > df['Open']).astype(int)
    m15 = df.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last',
        'Is_Green_M1': 'mean' 
    }).dropna()
    
    m15.rename(columns={'Is_Green_M1': 'Heartbeat'}, inplace=True)
    m15['M15_Direction'] = (m15['Close'] > m15['Open']).astype(int)

    last_candle = m15.iloc[-1]
    last_time = m15.index[-1].strftime('%Y-%m-%d %H:%M (UTC)')
    entry_price = last_candle['Close']
    high_price = last_candle['High']
    low_price = last_candle['Low']
    
    hb = last_candle['Heartbeat']
    m15_dir = last_candle['M15_Direction']
    
    # آناتومی کندل
    body_size = abs(last_candle['Close'] - last_candle['Open'])
    candle_range = high_price - low_price
    
    if candle_range == 0:
        body_ratio, lower_wick_ratio, upper_wick_ratio = 0, 0, 0
    else:
        body_ratio = body_size / candle_range
        lower_wick_ratio = (min(last_candle['Open'], last_candle['Close']) - low_price) / candle_range
        upper_wick_ratio = (high_price - max(last_candle['Open'], last_candle['Close'])) / candle_range

    print(f"Time: {last_time} | Price: {entry_price:.2f} | HB: {hb*100:.1f}% | Dir: {m15_dir}")

    # ==========================================
    # 🎯 منطق سیگنال و محاسبه قیمت‌ها
    # ==========================================
    signal_type = None
    signal_reason = ""
    confidence = 0

    # سیگنال خرید (BUY)
    if hb < 0.3 and m15_dir == 1 and lower_wick_ratio > 0.3:
        signal_type = "🟢 سیگنال خرید (BUY)"
        signal_reason = "فشار فروش زیاد بوده اما خریداران کنترل را گرفتند."
        confidence = 65
        
        # محاسبه حد ضرر و حد سود برای خرید
        stop_loss = low_price - 0.5  # کمی پایین‌تر از کف کندل برای امنیت
        risk = entry_price - stop_loss
        take_profit = entry_price + (risk * 2) # ریسک به ریوارد 1:2

    # سیگنال فروش (SELL)
    elif hb > 0.7 and m15_dir == 0 and upper_wick_ratio > 0.3:
        signal_type = "🔴 سیگنال فروش (SELL)"
        signal_reason = "فشار خرید زیاد بوده اما فروشندگان کنترل را گرفتند."
        confidence = 65
        
        # محاسبه حد ضرر و حد سود برای فروش
        stop_loss = high_price + 0.5 # کمی بالاتر از سقف کندل
        risk = stop_loss - entry_price
        take_profit = entry_price - (risk * 2)

    # ارسال پیام اگر سیگنال وجود داشت
    if signal_type:
        final_message = (
            f"🚨 <b>{signal_type}</b> 🚨\n"
            f"⏰ <b>زمان کندل:</b> {last_time}\n"
            f"💲 <b>قیمت ورود:</b> {entry_price:.2f}\n"
            f"🛑 <b>حد ضرر (SL):</b> {stop_loss:.2f}\n"
            f"🎯 <b>حد سود (TP):</b> {take_profit:.2f}\n\n"
            f"💓 <b>ضربان کندل:</b> {hb*100:.1f}%\n"
            f"📊 <b>وضعیت کندل M15:</b> {'سبز 🟢' if m15_dir == 1 else 'قرمز 🔴'}\n\n"
            f"📝 <b>دلیل:</b> {signal_reason}\n"
            f"🔥 <b>اطمینان:</b> {confidence}%\n\n"
            f"⚖️ <i>مدیریت سرمایه (ریسک ۱ تا ۲ درصدی) را فراموش نکنید.</i>"
        )
        print("سیگنال ارسال شد!")
        send_telegram_message(final_message)
    else:
        print("وضعیت خنثی است. پیامی ارسال نشد.")

if __name__ == "__main__":
    analyze_live_market()
