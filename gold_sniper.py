import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os

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
        print("داده‌ای دریافت نشد.")
        return

    df['Is_Green_M1'] = (df['Close'] > df['Open']).astype(int)
    m15 = df.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last',
        'Is_Green_M1': 'mean' 
    }).dropna()
    m15.rename(columns={'Is_Green_M1': 'Heartbeat'}, inplace=True)
    m15['M15_Direction'] = (m15['Close'] > m15['Open']).astype(int)

    last_candle = m15.iloc[-1]
    hb = last_candle['Heartbeat']
    m15_dir = last_candle['M15_Direction']

    signal_text = "⚖️ وضعیت بازار: خنثی (سیگنالی وجود ندارد)"
    if hb < 0.3 and m15_dir == 1:
        signal_text = "🟢 <b>سیگنال خرید (BUY) صادر شد!</b>\n\n🔥 فشار فروش زیاد بوده اما خریداران برنده شدند."
    elif hb > 0.7 and m15_dir == 0:
        signal_text = "🔴 <b>سیگنال فروش (SELL) صادر شد!</b>\n\n🔥 فشار خرید زیاد بوده اما فروشندگان برنده شدند."
    
    final_message = (
        f"📊 <b>گزارش زنده ربات Gold Sniper</b>\n"
        f"💓 <b>ضربان کندل:</b> {hb*100:.1f}%\n"
        f"📈 <b>جهت کندل:</b> {'سبز 🟢' if m15_dir == 1 else 'قرمز 🔴'}\n\n"
        f"{signal_text}"
    )
    
    print(final_message)
    send_telegram_message(final_message)

if __name__ == "__main__":
    analyze_live_market()
