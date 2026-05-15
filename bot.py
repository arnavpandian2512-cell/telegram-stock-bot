import os
import yfinance as yf
import requests
import pandas as pd
import time
import pytz
from datetime import datetime
from flask import Flask
from threading import Thread

# ================= TIME =================
IST = pytz.timezone("Asia/Kolkata")

# ================= TELEGRAM =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")


def send_telegram_msg(msg):
    try:
        if not BOT_TOKEN:
            print(msg)
            return
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
        print("📨 TELEGRAM:", msg)
    except Exception as e:
        print("Telegram error:", e)

# ================= FLASK =================
app = Flask(__name__)
@app.route("/")
def home():
    return "Trading Bot Running 🚀"

# ================= CAPITAL / RISK =================
INITIAL_CAPITAL = 100000
capital = INITIAL_CAPITAL
daily_pnl = 0
trade_count = 0
MAX_TRADES_PER_DAY = 3

# ================= SYMBOLS =================
SYMBOLS = [
    "RELIANCE.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS","TCS.NS",
    "SBIN.NS","LT.NS","ITC.NS","AXISBANK.NS","KOTAKBANK.NS",
    "ADANIENT.NS","ADANIPORTS.NS","HINDUNILVR.NS","BAJFINANCE.NS",
    "BHARTIARTL.NS","ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS",
    "TITAN.NS","ULTRACEMCO.NS"
]

opening_range = {}
alerted_today = set()
open_positions = {}

# ================= MARKET TIME FIX =================
def is_market_open():
    now = datetime.now(IST)
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end   = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return now.weekday() < 5 and start <= now <= end

# ================= INDICATORS =================
def calculate_vwap(df):
    return (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

def ema(df, period=20):
    return df['Close'].ewm(span=period).mean()

# ================= DAILY RESET =================
def daily_reset():
    global trade_count, daily_pnl, alerted_today, opening_range
    now = datetime.now(IST)

    if now.hour == 9 and now.minute == 10:
        print("🔄 Daily reset executed")
        trade_count = 0
        daily_pnl = 0
        alerted_today.clear()
        opening_range.clear()
        send_telegram_msg("🔄 New Trading Day Started")

    if now.hour == 15 and now.minute == 35:
        send_telegram_msg(f"📊 Daily PnL ₹{round(daily_pnl,2)}")

# ================= RISK CONTROL =================
def can_take_trade():
    return trade_count < MAX_TRADES_PER_DAY

# ================= OPEN / EXIT =================
def open_trade(symbol, direction, entry, sl, tgt):
    global capital, trade_count
    risk_per_trade = capital * 0.01
    qty = int(risk_per_trade / abs(entry - sl))
    if qty <= 0:
        return 0

    open_positions[symbol] = {
        "dir": direction,
        "entry": entry,
        "sl": sl,
        "tgt": tgt,
        "qty": qty
    }
    trade_count += 1
    return qty

def check_exit(symbol, price):
    global capital, daily_pnl
    if symbol not in open_positions:
        return

    pos = open_positions[symbol]
    pnl = 0

    if pos["dir"] == "BUY":
        if price >= pos["tgt"] or price <= pos["sl"]:
            pnl = (price - pos["entry"]) * pos["qty"]
    else:
        if price <= pos["tgt"] or price >= pos["sl"]:
            pnl = (pos["entry"] - price) * pos["qty"]

    if pnl != 0:
        capital += pnl
        daily_pnl += pnl
        send_telegram_msg(f"🏁 EXIT {symbol}  PnL ₹{round(pnl,2)}")
        del open_positions[symbol]

# ================= ORB FIX (REAL TIME BASED) =================
def capture_orb(symbol, df):
    if symbol in opening_range:
        return
    try:
        df = df.tz_localize(None)
        orb_df = df.between_time("09:15", "09:30")

        if len(orb_df) < 5:
            return

        high = orb_df['High'].max()
        low  = orb_df['Low'].min()
        opening_range[symbol] = (high, low)

        print(f"📦 ORB captured {symbol}: {round(high,2)} / {round(low,2)}")
    except Exception as e:
        print("ORB error:", symbol, e)

def check_orb(symbol, price):
    if symbol not in opening_range:
        return None
    high, low = opening_range[symbol]
    if price > high: return "BUY"
    if price < low:  return "SELL"
    return None

# ================= SCANNER (WITH DEBUG) =================
def scan():
    print("📡 Downloading market data from Yahoo...")
    try:
        data = yf.download(
            tickers=" ".join(SYMBOLS),
            period="1d",
            interval="1m",
            group_by='ticker',
            threads=True,
            progress=False
        )

        if data.empty:
            print("❌ Yahoo returned EMPTY data (rate limit)")
            return
        else:
            print("✅ Data received")

        for ticker in SYMBOLS:
            if ticker not in data: continue
            df = data[ticker].dropna()
            if df.empty or len(df) < 30:
                print("⚠️ Not enough data:", ticker)
                continue

            capture_orb(ticker, df)

            price = float(df['Close'].iloc[-1])
            vwap = calculate_vwap(df).iloc[-1]
            ema20 = ema(df).iloc[-1]

            check_exit(ticker, price)

            signal = check_orb(ticker, price)
            if not signal or ticker in alerted_today: continue
            if not can_take_trade(): continue

            if signal == "BUY" and (price < vwap or price < ema20): continue
            if signal == "SELL" and (price > vwap or price > ema20): continue

            alerted_today.add(ticker)

            high, low = opening_range[ticker]
            risk = (high - low) * 0.6

            if signal == "BUY":
                entry, sl, tgt = high, high-risk, high+(risk*2)
            else:
                entry, sl, tgt = low, low+risk, low-(risk*2)

            qty = open_trade(ticker, signal, entry, sl, tgt)

            send_telegram_msg(
                f"🚀 TRADE OPEN\n{ticker}\n{signal}\nEntry:{round(entry,2)}\nSL:{round(sl,2)}\nTarget:{round(tgt,2)}\nQty:{qty}"
            )

    except Exception as e:
        print("SCAN ERROR:", e)

# ================================
# MAIN STARTUP (PRODUCTION RENDER)
# ================================
if __name__ == "__main__":

    print("🤖 BOT STARTED — MAIN PROCESS")

    # send startup message
    send_telegram_msg("🚀 Bot LIVE on Render")

    # start Flask ONLY for health check in background
    def run_flask():
        print("🌐 Flask health server started")
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    Thread(target=run_flask).start()

    # ================================
    # MAIN TRADING LOOP (IMPORTANT)
    # ================================
    while True:
        try:
            now = datetime.now(IST)
            print(f"\n⏰ Heartbeat {now.strftime('%H:%M:%S')}")

            daily_reset()

            if is_market_open():
                print("📈 Market OPEN — scanning...")
                scan()
            else:
                print("😴 Market closed")

            time.sleep(90)  # scan every 90 sec

        except Exception as e:
            print("🔥 MAIN LOOP ERROR:", e)
            send_telegram_msg(f"Bot Error: {e}")
            time.sleep(60)