# ================================
# NIFTY50 ORB + VWAP PAPER TRADING BOT
# Cloud Ready (Render)
# ================================

import os
import yfinance as yf
import requests
import pandas as pd
import time
import pytz
from datetime import datetime, time as dtime

# ========= TELEGRAM FROM ENV =========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# ========= TIMEZONE =========
IST = pytz.timezone("Asia/Kolkata")

# ========= PAPER TRADING =========
capital = 100000
RISK_PER_TRADE = 0.01
open_trades = {}
opening_range = {}
alerted_today = set()
orb_captured = set()

# ========= TELEGRAM =========
def send_telegram_msg(message):
    if not TELEGRAM_TOKEN:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url,json={"chat_id":CHAT_ID,"text":message})

# ========= NIFTY50 LIST =========
def get_nifty50_symbols():
    url="https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    df=pd.read_csv(url)
    return [s+".NS" for s in df['Symbol'].tolist()]

SYMBOLS = get_nifty50_symbols()

# ========= MARKET HOURS =========
def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    if now.time() < dtime(9,15):
        return False
    if now.time() > dtime(15,30):
        return False
    return True

# ========= POSITION SIZING =========
def calculate_qty(entry, sl):
    risk_amount = capital * RISK_PER_TRADE
    risk_per_share = abs(entry - sl)
    qty = int(risk_amount / risk_per_share)
    return max(qty,1)

def open_trade(ticker, direction, entry, sl, target):
    qty = calculate_qty(entry, sl)
    open_trades[ticker] = {"dir":direction,"entry":entry,"sl":sl,"target":target,"qty":qty}
    return qty

# ========= EXIT MANAGEMENT =========
def check_exit(ticker, price):
    global capital
    if ticker not in open_trades:
        return None

    t = open_trades[ticker]

    # LONG EXIT
    if t["dir"]=="BUY":
        if price <= t["sl"]:
            loss = (t["entry"]-t["sl"])*t["qty"]
            capital -= loss
            del open_trades[ticker]
            return f"❌ SL HIT {ticker}\nLoss ₹{round(loss,2)}\nCapital ₹{round(capital,2)}"

        if price >= t["target"]:
            profit = (t["target"]-t["entry"])*t["qty"]
            capital += profit
            del open_trades[ticker]
            return f"✅ TARGET HIT {ticker}\nProfit ₹{round(profit,2)}\nCapital ₹{round(capital,2)}"

    # SHORT EXIT
    if t["dir"]=="SELL":
        if price >= t["sl"]:
            loss = (t["sl"]-t["entry"])*t["qty"]
            capital -= loss
            del open_trades[ticker]
            return f"❌ SL HIT {ticker}\nLoss ₹{round(loss,2)}\nCapital ₹{round(capital,2)}"

        if price <= t["target"]:
            profit = (t["entry"]-t["target"])*t["qty"]
            capital += profit
            del open_trades[ticker]
            return f"✅ TARGET HIT {ticker}\nProfit ₹{round(profit,2)}\nCapital ₹{round(capital,2)}"

# ========= INDICATORS =========
def calculate_vwap(df):
    tp=(df['High']+df['Low']+df['Close'])/3
    return (tp*df['Volume']).cumsum().iloc[-1]/df['Volume'].cumsum().iloc[-1]

# ========= ORB CAPTURE =========
def capture_opening_range(ticker, df):
    now = datetime.now(IST).time()

    # Capture only once per day
    if ticker in orb_captured:
        return

    if dtime(9,15) <= now <= dtime(9,35):
        orb_df = df.between_time("09:15","09:30")
        if len(orb_df) < 5:
            return

        high = float(orb_df["High"].max())
        low  = float(orb_df["Low"].min())

        opening_range[ticker] = (high,low)
        orb_captured.add(ticker)

# ========= ORB SIGNAL =========
def check_orb_breakout(ticker, price):
    if ticker not in opening_range:
        return None
    high,low = opening_range[ticker]
    if price > high: return "BUY"
    if price < low:  return "SELL"
    return None

# ========= DAILY RESET =========
def daily_reset():
    global alerted_today, orb_captured, opening_range
    now = datetime.now(IST).time()
    if now > dtime(15,31):
        alerted_today.clear()
        orb_captured.clear()
        opening_range.clear()

# ========= MAIN SCANNER =========
def scan_and_alert():

    global capital
    now = datetime.now(IST)
    print("\n⏱ Running scan:", now)

    for ticker in SYMBOLS:
        try:
            df = yf.download(ticker,period="1d",interval="1m",progress=False)
            if df.empty:
                continue

            # ⭐ FIX MULTI INDEX BUG
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df[['Open','High','Low','Close','Volume']]

            capture_opening_range(ticker,df)

            price = float(df['Close'].iloc[-1])
            ema20 = float(df['Close'].ewm(span=20).mean().iloc[-1])
            vwap  = float(calculate_vwap(df))

            # check exits first
            exit_msg = check_exit(ticker,price)
            if exit_msg:
                send_telegram_msg(exit_msg)

            orb_signal = check_orb_breakout(ticker,price)
            if not orb_signal or ticker in alerted_today:
                continue

            # VWAP filter
            if (orb_signal=="BUY" and price<vwap) or (orb_signal=="SELL" and price>vwap):
                continue

            alerted_today.add(ticker)

            high,low = opening_range[ticker]
            risk = (high-low)*0.6

            if orb_signal=="BUY":
                entry=high; sl=entry-risk; tgt=entry+(risk*2)
            else:
                entry=low; sl=entry+risk; tgt=entry-(risk*2)

            qty = open_trade(ticker,orb_signal,entry,sl,tgt)

            msg=(f"📢 PAPER TRADE OPEN\n{ticker}\n{orb_signal}\n"
                 f"Entry ₹{entry:.2f}\nSL ₹{sl:.2f}\nTarget ₹{tgt:.2f}\n"
                 f"Qty {qty}\nCapital ₹{round(capital,2)}")

            send_telegram_msg(msg)

        except Exception as e:
            print("Error",ticker,e)

# ========= LOOP =========
print("BOT STARTED 🚀")
send_telegram_msg("🤖 ORB Paper Trading Bot Running")

while True:
    if is_market_open():
        print("✅ Market OPEN")
        scan_and_alert()
    else:
        print("😴 Market closed")

    daily_reset()
    time.sleep(300)  # 5 minutes