import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import datetime

BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال: {e}")

def find_invisible_walls():
    ticker = yf.Ticker("GC=F")
    df_h1 = ticker.history(period="60d", interval="1h")
    if df_h1.empty:
        return [], []
    
    df_h1['Pivot_High'] = df_h1['High'][(df_h1['High'] == df_h1['High'].rolling(window=5, center=True).max())]
    df_h1['Pivot_Low'] = df_h1['Low'][(df_h1['Low'] == df_h1['Low'].rolling(window=5, center=True).min())]
    
    resistances = df_h1['Pivot_High'].dropna().round(0).value_counts().head(3).index.tolist()
    supports = df_h1['Pivot_Low'].dropna().round(0).value_counts().head(3).index.tolist()
    return sorted(resistances), sorted(supports, reverse=True)

def analyze_market():
    resistances, supports = find_invisible_walls()
    
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period="2d", interval="1m")
    if df.empty:
        return

    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')

    df['Is_Green_M1'] = (df['Close'] > df['Open']).astype(int)
    m15 = df.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last',
        'Is_Green_M1': 'mean' 
    }).dropna()
    
    m15.rename(columns={'Is_Green_M1': 'Heartbeat'}, inplace=True)
    m15['M15_Direction'] = (m15['Close'] > m15['Open']).astype(int)

    last_m15 = m15.iloc[-2] 
    current_time = m15.index[-2]
    entry_price = last_m15['Close']
    hb = last_m15['Heartbeat']
    m15_dir = last_m15['M15_Direction']

    # پیدا کردن نزدیک‌ترین دیوارها
    nearest_res = min([r for r in resistances if r > entry_price], default=0)
    nearest_sup = max([s for s in supports if s < entry_price], default=0)

    signal_type = None
    reason = ""

    # قانون آسون‌تر برای سیگنال
    if m15_dir == 1 and hb < 0.45:
        signal_type = "🟢 سیگنال خرید (BUY)"
        reason = "کندل M15 سبز بسته شد و فشار فروش درون کندل وجود داشت (ضربان پایین)."
        stop_loss = last_m15['Low'] - 1.0
        risk = entry_price - stop_loss
        take_profit = entry_price + (risk * 2)

    elif m15_dir == 0 and hb > 0.55:
        signal_type = "🔴 سیگنال فروش (SELL)"
        reason = "کندل M15 قرمز بسته شد و فشار خرید درون کندل وجود داشت (ضربان بالا)."
        stop_loss = last_m15['High'] + 1.0
        risk = stop_loss - entry_price
        take_profit = entry_price - (risk * 2)

    # ارسال پیام
    if signal_type:
        final_message = (
            f"🧱 <b>شکارچی دیوارها (Learning Mode)</b> 🧱\n\n"
            f"🚨 <b>{signal_type}</b> 🚨\n"
            f"⏰ <b>زمان:</b> {current_time.strftime('%H:%M')} (UTC)\n\n"
            f"💲 <b>قیمت ورود:</b> {entry_price:.2f}\n"
            f"🛑 <b>حد ضرر (SL):</b> {stop_loss:.2f}\n"
            f"🎯 <b>حد سود (TP):</b> {take_profit:.2f}\n\n"
            f"📊 <b>وضعیت:</b> ضربان: {hb*100:.1f}% | جهت: {'سبز' if m15_dir == 1 else 'قرمز'}\n\n"
            f"🧱 <b>دیوارهای نامرئی:</b>\n"
            f"مقاومت بالای سر: {nearest_res if nearest_res != 0 else 'نامشخص'}\n"
            f"حمایت زیر پا: {nearest_sup if nearest_sup != 0 else 'نامشخص'}\n\n"
            f"🎓 <b>درس:</b> {reason}\n"
            f"⚖️ <i>مدیریت سرمایه فراموش نشود.</i>"
        )
        print("سیگنال ارسال شد!")
        send_telegram_message(final_message)
    else:
        print(f"خنثی. ضربان: {hb*100:.1f}% | جهت: {m15_dir} | نزدیک‌ترین دیوارها: {nearest_sup} / {nearest_res}")

if __name__ == "__main__":
    analyze_market()
