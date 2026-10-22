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

def analyze_market():
    # دریافت داده‌های ۱ دقیقه‌ای برای ۵ روز اخیر (برای محاسبات بهتر)
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period="5d", interval="1m")
    
    if df.empty:
        print("داده‌ای دریافت نشد.")
        return

    # اطمینان از اینکه ایندکس بر اساس UTC است
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')

    # ۱. محاسبه کندل‌های M15 و ضربان
    df['Is_Green_M1'] = (df['Close'] > df['Open']).astype(int)
    m15 = df.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last',
        'Is_Green_M1': 'mean' 
    }).dropna()
    m15.rename(columns={'Is_Green_M1': 'Heartbeat'}, inplace=True)
    m15['M15_Direction'] = (m15['Close'] > m15['Open']).astype(int)
    
    # محاسبه ATR (میانگین دامنه واقعی)
    m15['H-L'] = m15['High'] - m15['Low']
    m15['H-PC'] = abs(m15['High'] - m15['Close'].shift(1))
    m15['L-PC'] = abs(m15['Low'] - m15['Close'].shift(1))
    m15['TR'] = m15[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    m15['ATR'] = m15['TR'].rolling(window=14).mean()

    # ۲. محاسبه کندل‌های H1 و روند (EMA 20)
    h1 = df.resample('1h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
    }).dropna()
    h1['EMA_20'] = h1['Close'].ewm(span=20, adjust=False).mean()

    # استخراج آخرین کندل بسته شده (نه کندل در حال تشکیل)
    last_m15 = m15.iloc[-2] 
    last_h1 = h1.iloc[-1]
    current_time = m15.index[-2]
    
    # ==========================================
    # 🛡️ فیلتر ۱: سشن زمانی (فقط لندن و نیویورک)
    # ==========================================
    # ساعت UTC: 07:00 تا 20:00
    if not (7 <= current_time.hour <= 20):
        print(f"زمان فعلی ({current_time.strftime('%H:%M')} UTC) خارج از سشن معاملاتی است. ربات ساکت است.")
        return

    # ==========================================
    # 🧠 فیلتر ۲: روند H1
    # ==========================================
    entry_price = last_m15['Close']
    atr = last_m15['ATR']
    hb = last_m15['Heartbeat']
    m15_dir = last_m15['M15_Direction']
    
    h1_trend = "UP" if last_h1['Close'] > last_h1['EMA_20'] else "DOWN"
    
    # اگر ATR نان بود (داده کافی نبود)
    if pd.isna(atr) or atr == 0:
        print("ATR محاسبه نشد. منتظر داده بیشتر می‌مانیم.")
        return

    signal_type = None
    reason = ""

    # ==========================================
    # 🎯 منطق شلیک (خرید و فروش)
    # ==========================================
    
    # سیگنال خرید: روند H1 صعودی + ضربان زیر 40% + کندل M15 سبز
    if h1_trend == "UP" and hb < 0.4 and m15_dir == 1:
        signal_type = "🟢 سیگنال خرید (BUY)"
        reason = "روند H1 صعودی است. فشار فروش در M15 زیاد بوده (ضربان پایین)، اما خریداران برنده شدند."
        
        stop_loss = entry_price - (atr * 1.5)
        risk = entry_price - stop_loss
        take_profit = entry_price + (risk * 2)

    # سیگنال فروش: روند H1 نزولی + ضربان بالای 60% + کندل M15 قرمز
    elif h1_trend == "DOWN" and hb > 0.6 and m15_dir == 0:
        signal_type = "🔴 سیگنال فروش (SELL)"
        reason = "روند H1 نزولی است. فشار خرید در M15 زیاد بوده (ضربان بالا)، اما فروشندگان برنده شدند."
        
        stop_loss = entry_price + (atr * 1.5)
        risk = stop_loss - entry_price
        take_profit = entry_price - (risk * 2)

    # ارسال پیام در صورت وجود سیگنال
    if signal_type:
        final_message = (
            f"🦖 <b>شکارچی کوانتومی (Quantum Sniper)</b> 🎯\n\n"
            f"🚨 <b>{signal_type}</b> 🚨\n"
            f"⏰ <b>زمان:</b> {current_time.strftime('%Y-%m-%d %H:%M')} (UTC)\n\n"
            f"💲 <b>قیمت ورود:</b> {entry_price:.2f}\n"
            f"🛑 <b>حد ضرر (SL):</b> {stop_loss:.2f} (بر اساس ATR)\n"
            f"🎯 <b>حد سود (TP):</b> {take_profit:.2f}\n\n"
            f"📊 <b>تحلیل:</b>\n"
            f"روند H1: {h1_trend} {'📈' if h1_trend == 'UP' else '📉'}\n"
            f"ضربان M15: {hb*100:.1f}%\n"
            f"جهت M15: {'سبز 🟢' if m15_dir == 1 else 'قرمز 🔴'}\n\n"
            f"🎓 <b>درس:</b> {reason}\n\n"
            f"⚖️ <i>ریسک به ریوارد 1:2. مدیریت سرمایه فراموش نشود.</i>"
        )
        print("سیگنال شلیک شد!")
        send_telegram_message(final_message)
    else:
        print(f"وضعیت خنثی است. روند: {h1_trend} | ضربان: {hb*100:.1f}% | جهت: {m15_dir}")

if __name__ == "__main__":
    analyze_market()
