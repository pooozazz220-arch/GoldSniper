import requests
import pandas as pd
import numpy as np
import os
import datetime

# خواندن کلیدها از گاوصندوق گیت‌هاب
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
TWELVEDATA_API_KEY = os.environ.get('TWELVEDATA_API_KEY')

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"خطا در ارسال: {e}")

def analyze_real_market():
    # دریافت داده‌های 1 دقیقه‌ای از TwelveData برای طلا (XAU/USD)
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1min&outputsize=500&apikey={TWELVEDATA_API_KEY}"
    
    try:
        response = requests.get(url, timeout=15).json()
        if 'values' not in response:
            print(f"خطای API: {response.get('message', 'نامشخص')}")
            return
            
        # تبدیل دیتا به دیتافریم پانداس
        df = pd.DataFrame(response['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        
        # مرتب‌سازی صعودی (از قدیم به جدید)
        df = df.sort_index()
        
        # تبدیل ستون‌ها به عدد
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)

        # ۱. محاسبه کندل‌های M15 و نبض (Heartbeat)
        df['Is_Green_M1'] = (df['close'] > df['open']).astype(int)
        m15 = df.resample('15min').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
            'Is_Green_M1': 'mean' 
        }).dropna()
        
        m15.rename(columns={'Is_Green_M1': 'Heartbeat'}, inplace=True)
        m15['M15_Direction'] = (m15['close'] > m15['open']).astype(int)

        # استخراج آخرین کندل بسته شده
        last_candle = m15.iloc[-2]
        current_time = m15.index[-2]
        entry_price = last_candle['close']
        hb = last_candle['Heartbeat']
        m15_dir = last_candle['M15_Direction']

        print(f"Time: {current_time} | Price: {entry_price} | HB: {hb*100:.1f}% | Dir: {m15_dir}")

        # قانون آسون‌تر برای سیگنال (همون نبض کندل خودمون)
        signal_type = None
        reason = ""

        if m15_dir == 1 and hb < 0.45:
            signal_type = "🟢 سیگنال خرید (BUY)"
            reason = "کندل M15 سبز بسته شد و فشار فروش درون کندل وجود داشت (نبض پایین)."
            stop_loss = last_candle['low'] - 1.0
            risk = entry_price - stop_loss
            take_profit = entry_price + (risk * 2)

        elif m15_dir == 0 and hb > 0.55:
            signal_type = "🔴 سیگنال فروش (SELL)"
            reason = "کندل M15 قرمز بسته شد و فشار خرید درون کندل وجود داشت (نبض بالا)."
            stop_loss = last_candle['high'] + 1.0
            risk = stop_loss - entry_price
            take_profit = entry_price - (risk * 2)

        # ارسال پیام در صورت وجود سیگنال
        if signal_type:
            final_message = (
                f"⚡ <b>سیگنال طلای واقعی (Live XAUUSD)</b> ⚡\n\n"
                f"🚨 <b>{signal_type}</b> 🚨\n"
                f"⏰ <b>زمان:</b> {current_time.strftime('%H:%M')} (UTC)\n\n"
                f"💲 <b>قیمت ورود:</b> {entry_price:.2f}\n"
                f"🛑 <b>حد ضرر (SL):</b> {stop_loss:.2f}\n"
                f"🎯 <b>حد سود (TP):</b> {take_profit:.2f}\n\n"
                f"📊 <b>نبض کندل:</b> {hb*100:.1f}%\n"
                f"📈 <b>جهت کندل:</b> {'سبز 🟢' if m15_dir == 1 else 'قرمز 🔴'}\n\n"
                f"🎓 <b>درس:</b> {reason}\n"
                f"⚖️ <i>مدیریت سرمایه فراموش نشود.</i>"
            )
            print("سیگنال شلیک شد!")
            send_telegram_message(final_message)
        else:
            print("وضعیت خنثی است. پیامی ارسال نشد.")

    except Exception as e:
        print(f"خطا در پردازش دیتا: {e}")

if __name__ == "__main__":
    analyze_real_market()
