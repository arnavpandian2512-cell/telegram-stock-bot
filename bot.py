# ================================
# NIFTY50 ORB + VWAP + EMA + RISK CONTROL BOT
# FINAL PRO TRADING VERSION 🚀
# ================================

import os
import yfinance as yf
import requests
import pandas as pd
import time
import pytz
from datetime import datetime, time as dtime
from flask import Flask
from threading import Thread

# ========= TELEGRAM =========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ========= CONFIG =========
MAX_TRADES_PER_DAY = 5
MAX_DAILY_LOSS_PCT = 2   # 🚨 stop trading after -2%

# ========= FLASK =========
app = Flask(__name__)

# ========= TIME =========
IST = pytz.timezone("Asia/Kolkata")

# ========= CAPITAL =========
initial_capital = 100000
capital = initial_capital

# ========= RISK =========
RISK_PER_TRADE = 0.01

# ========= STATE =========
open_trades = {}
opening_range = {}
alerted_today = set()
orb_captured = set()

# ========= DAILY STATS =========
daily_trades = 0
daily_wins = 0
daily_losses = 0
daily_pnl = 0
daily_report_sent = False

equity_curve = []

# ========= TELEGRAM =========
def send_telegram_msg(message):
    if not TELEGRAM_TOKEN:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message})

# ========= SYMBOLS =========
def get_nifty50_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    df = pd.read_csv(url)
    return [s + ".NS" for s in df['Symbol'].tolist()]

SYMBOLS = get_nifty50_symbols()

# ========= MARKET =========
def is_market_open():
    now = datetime.now(IST)
    return now.weekday() < 5 and dtime(9, 15) <= now.time() <= dtime(15, 30)

# ========= RISK CONTROL =========
def can_take_trade():
    global capital
    if daily_trades >= MAX_TRADES_PER_DAY:
        return False

    drawdown = ((initial_capital - capital) / initial_capital) * 100
    if drawdown >= MAX_DAILY_LOSS_PCT:
        return False

    return True

# ========= INDICATORS =========
def calculate_vwap(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).cumsum().iloc[-1] / df['Volume'].cumsum().iloc[-1]

def ema(df, n=20):
    return df['Close'].ewm(span=n).mean().iloc[-1]

# ========= ORB =========
def capture_orb(ticker, df):
    now = datetime.now(IST).time()
    if ticker in orb_captured:
        return

    if dtime(9, 15) <= now <= dtime(9, 35):
        orb_df = df.between_time("09:15", "09:30")
        if len(orb_df) < 5:
            return

        opening_range[ticker] = (
            float(orb_df["High"].max()),
            float(orb_df["Low"].min())
        )
        orb_captured.add(ticker)

def check_orb(ticker, price):
    if ticker not in opening_range:
        return None
    high, low = opening_range[ticker]

    if price > high:
        return "BUY"
    if price < low:
        return "SELL"

# ========= TRADE ENGINE =========
def calculate_qty(entry, sl):
    risk = capital * RISK_PER_TRADE
    return max(int(risk / abs(entry - sl)), 1)

def open_trade(ticker, dir, entry, sl, tgt):
    qty = calculate_qty(entry, sl)
    open_trades[ticker] = {"dir": dir, "entry": entry, "sl": sl, "target": tgt, "qty": qty}
    return qty

def close_trade(ticker, price):
    global capital, daily_trades, daily_wins, daily_losses, daily_pnl

    t = open_trades[ticker]
    qty = t["qty"]

    if t["dir"] == "BUY":
        pnl = (price - t["entry"]) * qty
    else:
        pnl = (t["entry"] - price) * qty

    capital += pnl
    daily_trades += 1
    daily_pnl += pnl

    if pnl > 0:
        daily_wins += 1
    else:
        daily_losses += 1

    del open_trades[ticker]

    send_telegram_msg(
        f"{ticker} EXIT\nPnL: ₹{round(pnl,2)}\nCapital: ₹{round(capital,2)}"
    )

def check_exit(ticker, price):
    if ticker not in open_trades:
        return

    t = open_trades[ticker]

    if t["dir"] == "BUY":
        if price <= t["sl"]:
            close_trade(ticker, t["sl"])
        elif price >= t["target"]:
            close_trade(ticker, t["target"])
    else:
        if price >= t["sl"]:
            close_trade(ticker, t["sl"])
        elif price <= t["target"]:
            close_trade(ticker, t["target"])

# ========= SCANNER =========
def scan():
    global capital

    for ticker in SYMBOLS:
        try:
            df = yf.download(ticker, period="1d", interval="1m", progress=False)
            if df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df[['Open','High','Low','Close','Volume']]

            capture_orb(ticker, df)

            price = float(df['Close'].iloc[-1])
            vwap = calculate_vwap(df)
            ema20 = ema(df)

            check_exit(ticker, price)

            signal = check_orb(ticker, price)

            if not signal or ticker in alerted_today:
                continue

            if not can_take_trade():
                continue

            # ===== STRATEGY FILTERS =====
            if signal == "BUY":
                if price < vwap or price < ema20:
                    continue
            if signal == "SELL":
                if price > vwap or price > ema20:
                    continue

            alerted_today.add(ticker)

            high, low = opening_range[ticker]
            risk = (high - low) * 0.6

            if signal == "BUY":
                entry = high
                sl = entry - risk
                tgt = entry + (risk * 2)
            else:
                entry = low
                sl = entry + risk
                tgt = entry - (risk * 2)

            qty = open_trade(ticker, signal, entry, sl, tgt)

            send_telegram_msg(
                f"TRADE OPEN\n{ticker}\n{signal}\nEntry:{entry}\nSL:{sl}\nTarget:{tgt}\nQty:{qty}"
            )

        except Exception as e:
            print("Error:", ticker, e)

# ========= LOOP =========
def run():
    print("BOT STARTED 🚀")
    send_telegram_msg("Bot LIVE 🚀")

    while True:
        if is_market_open():
            scan()

        time.sleep(300)

Thread(target=run, daemon=True).start()

@app.route("/")
def home():
    return "Bot Running 🚀"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))