
import os
import time
import json
import requests
import pandas as pd
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("TWELVEDATA_API_KEY")

SYMBOL = "XAU/USD"
CHECK_SECONDS = 20

# این سطح‌ها نمونه‌اند؛ با قیمت فعلی تنظیمشان کن
LEVELS = [4156.0, 4165.0, 4175.0]

# تنظیمات آزمایشی هشدار سریع
JUMP_USD = 1.5
JUMP_SECONDS = 60
COOLDOWN_SECONDS = 300
STATE_FILE = "gold_sniper_state.json"

last_alert = {}
recent_prices = []


def send_telegram_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("خطا: BOT_TOKEN یا CHAT_ID تنظیم نشده.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )
        response.raise_for_status()
        return response.json().get("ok", False)
    except Exception as e:
        print("خطا در تلگرام:", e)
        return False


def alert_once(key, message, cooldown=COOLDOWN_SECONDS):
    now = time.time()

    if now - last_alert.get(key, 0) < cooldown:
        return

    if send_telegram_message(message):
        last_alert[key] = now


def get_latest_price():
    url = "https://api.twelvedata.com/price"

    response = requests.get(
        url,
        params={
            "symbol": SYMBOL,
            "apikey": API_KEY
        },
        timeout=10
    )
    response.raise_for_status()
    data = response.json()

    if "price" not in data:
        raise RuntimeError(str(data))

    return float(data["price"])


def check_fast_alerts(price):
    now = time.time()
    recent_prices.append((now, price))

    while recent_prices and now - recent_prices[0][0] > JUMP_SECONDS:
        recent_prices.pop(0)

    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    # هشدار عبور از سطح
    if len(recent_prices) >= 2:
        previous = recent_prices[-2][1]

        for level in LEVELS:
            if previous < level <= price:
                alert_once(
                    f"level_up_{level}",
                    f"⚡ XAUUSD شکست رو به بالا\n"
                    f"سطح: {level}\nقیمت: {price:.2f}\n{stamp}"
                )

            elif previous > level >= price:
                alert_once(
                    f"level_down_{level}",
                    f"⚡ XAUUSD شکست رو به پایین\n"
                    f"سطح: {level}\nقیمت: {price:.2f}\n{stamp}"
                )

    # هشدار جهش قیمت
    if len(recent_prices) >= 2:
        change = price - recent_prices[0][1]

        if abs(change) >= JUMP_USD:
            direction = "جهش صعودی" if change > 0 else "ریزش سریع"

            alert_once(
                "price_jump",
                f"🚨 XAUUSD {direction}\n"
                f"تغییر قیمت: {change:.2f}$\n"
                f"قیمت فعلی: {price:.2f}\n{stamp}",
                cooldown=180
            )


def check_m15_signal():
    url = "https://api.twelvedata.com/time_series"

    response = requests.get(
        url,
        params={
            "symbol": SYMBOL,
            "interval": "15min",
            "outputsize": 60,
            "timezone": "UTC",
            "apikey": API_KEY
        },
        timeout=15
    )
    response.raise_for_status()
    data = response.json()

    if "values" not in data:
        raise RuntimeError(str(data))

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df = df.sort_values("datetime").reset_index(drop=True)

    # فقط کندل‌هایی که زمان بسته‌شدنشان گذشته است
    now = pd.Timestamp.now(tz="UTC")
    df = df[df["datetime"] + pd.Timedelta(minutes=15) <= now]

    if len(df) < 22:
        return

    # جلوگیری از هشدار تکراری روی همان کندل
    candle_time = df.iloc[-1]["datetime"].isoformat()

    if last_alert.get("last_m15_candle") == candle_time:
        return

    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()

    candle = df.iloc[-1]
    previous = df.iloc[-2]

    direction = None

    if candle["close"] > candle["open"] and candle["close"] > candle["ema20"]:
        direction = "BUY"

    elif candle["close"] < candle["open"] and candle["close"] < candle["ema20"]:
        direction = "SELL"

    if direction:
        message = (
            f"📊 هشدار تکنیکال XAUUSD: {direction}\n"
            f"زمان کندل: {candle_time}\n"
            f"قیمت بسته‌شدن: {candle['close']:.2f}\n"
            f"EMA20: {candle['ema20']:.2f}\n"
            "این هشدار به‌تنهایی تأیید ورود نیست؛ "
            "حد ضرر و ریسک را بررسی کن."
        )

        if send_telegram_message(message):
            last_alert["last_m15_candle"] = candle_time
    else:
        last_alert["last_m15_candle"] = candle_time


def main():
    if not API_KEY:
        raise SystemExit("متغیر TWELVEDATA_API_KEY تنظیم نشده است.")

    print("GoldSniper شروع شد؛ برای توقف Ctrl+C را بزن.")

    last_m15_check = 0

    while True:
        try:
            price = get_latest_price()
            print("XAUUSD:", price)

            check_fast_alerts(price)

            # بررسی تکنیکال هر 60 ثانیه
            if time.time() - last_m15_check >= 60:
                check_m15_signal()
                last_m15_check = time.time()

        except Exception as e:
            print("خطا:", e)

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()
