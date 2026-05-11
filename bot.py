# ================================
# NIFTY50 ORB + VWAP PAPER TRADING BOT
# WITH DAILY REPORT + CSV LOG
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
import os


app = Flask(__name__)

@app.route("/")
def home():
    return "Stock bot running!"

# ========= TELEGRAM =========
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

# ===== DAILY STATS =====
daily_trades = 0
daily_wins = 0
daily_pnl = 0
daily_report_sent = False

# ========= TELEGRAM =========
def send_telegram_msg(message):
    if not TELEGRAM_TOKEN:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url,json={"chat_id":CHAT_ID,"text":message})

# ========= CSV LOGGER =========
def log_trade_csv(symbol, direction, entry, exit_price, qty, pnl):
    file = "trade_log.csv"
    df = pd.DataFrame([{
        "Date": datetime.now(IST),
        "Symbol": symbol,
        "Direction": direction,
        "Entry": entry,
        "Exit": exit_price,
        "Qty": qty,
        "PnL": pnl,
        "Capital": capital
    }])
    df.to_csv(file, mode='a', header=not os.path.exists(file), index=False)

# ========= NIFTY50 =========
def get_nifty50_symbols():
    url="https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    df=pd.read_csv(url)
    return [s+".NS" for s in df['Symbol'].tolist()]

SYMBOLS = get_nifty50_symbols()

# ========= MARKET HOURS =========
def is_market_open():
    now = datetime.now(IST)
    return now.weekday()<5 and dtime(9,15)<=now.time()<=dtime(15,30)

# ========= POSITION SIZE =========
def calculate_qty(entry, sl):
    risk_amount = capital * RISK_PER_TRADE
    risk_per_share = abs(entry - sl)
    return max(int(risk_amount / risk_per_share),1)

def open_trade(ticker, direction, entry, sl, target):
    qty = calculate_qty(entry, sl)
    open_trades[ticker]={"dir":direction,"entry":entry,"sl":sl,"target":target,"qty":qty}
    return qty

# ========= EXIT MANAGEMENT =========
def close_trade(ticker, price, reason):
    global capital, daily_trades, daily_wins, daily_pnl

    t = open_trades[ticker]
    qty = t["qty"]

    if t["dir"]=="BUY":
        pnl = (price - t["entry"]) * qty
    else:
        pnl = (t["entry"] - price) * qty

    capital += pnl
    daily_trades += 1
    daily_pnl += pnl
    if pnl > 0:
        daily_wins += 1

    log_trade_csv(ticker, t["dir"], t["entry"], price, qty, pnl)

    del open_trades[ticker]

    send_telegram_msg(
        f"{reason} {ticker}\nPnL ₹{round(pnl,2)}\nCapital ₹{round(capital,2)}"
    )

def check_exit(ticker, price):
    if ticker not in open_trades:
        return
    t = open_trades[ticker]
    if t["dir"]=="BUY":
        if price <= t["sl"]: close_trade(ticker, t["sl"], "❌ SL HIT")
        elif price >= t["target"]: close_trade(ticker, t["target"], "✅ TARGET HIT")
    else:
        if price >= t["sl"]: close_trade(ticker, t["sl"], "❌ SL HIT")
        elif price <= t["target"]: close_trade(ticker, t["target"], "✅ TARGET HIT")

# ========= INDICATORS =========
def calculate_vwap(df):
    tp=(df['High']+df['Low']+df['Close'])/3
    return (tp*df['Volume']).cumsum().iloc[-1]/df['Volume'].cumsum().iloc[-1]

# ========= ORB =========
def capture_opening_range(ticker, df):
    now = datetime.now(IST).time()
    if ticker in orb_captured: return
    if dtime(9,15)<=now<=dtime(9,35):
        orb_df=df.between_time("09:15","09:30")
        if len(orb_df)<5: return
        opening_range[ticker]=(float(orb_df["High"].max()),float(orb_df["Low"].min()))
        orb_captured.add(ticker)

def check_orb_breakout(ticker, price):
    if ticker not in opening_range: return None
    high,low=opening_range[ticker]
    if price>high: return "BUY"
    if price<low: return "SELL"

# ========= DAILY REPORT =========
def send_daily_report():
    global daily_trades,daily_wins,daily_pnl,daily_report_sent

    now=datetime.now(IST).time()
    if now < dtime(15,31) or daily_report_sent:
        return

    winrate = (daily_wins/daily_trades*100) if daily_trades>0 else 0

    msg=(f"📊 DAILY REPORT\n"
         f"Trades: {daily_trades}\n"
         f"Wins: {daily_wins}\n"
         f"Winrate: {winrate:.1f}%\n"
         f"PnL: ₹{round(daily_pnl,2)}\n"
         f"Capital: ₹{round(capital,2)}")

    send_telegram_msg(msg)
    daily_report_sent=True

def daily_reset():
    global daily_trades,daily_wins,daily_pnl,daily_report_sent
    if datetime.now(IST).time()>dtime(15,35):
        daily_trades=daily_wins=daily_pnl=0
        daily_report_sent=False
        alerted_today.clear()
        orb_captured.clear()
        opening_range.clear()

# ========= SCANNER =========
def scan_and_alert():
    for ticker in SYMBOLS:
        try:
            df=yf.download(ticker,period="1d",interval="1m",progress=False)
            if df.empty: continue
            if isinstance(df.columns,pd.MultiIndex):
                df.columns=df.columns.get_level_values(0)

            df=df[['Open','High','Low','Close','Volume']]

            capture_opening_range(ticker,df)
            price=float(df['Close'].iloc[-1])
            vwap=float(calculate_vwap(df))

            check_exit(ticker,price)

            signal=check_orb_breakout(ticker,price)
            if not signal or ticker in alerted_today: continue
            if (signal=="BUY" and price<vwap) or (signal=="SELL" and price>vwap): continue

            alerted_today.add(ticker)

            high,low=opening_range[ticker]
            risk=(high-low)*0.6

            if signal=="BUY":
                entry=high; sl=entry-risk; tgt=entry+(risk*2)
            else:
                entry=low; sl=entry+risk; tgt=entry-(risk*2)

            qty=open_trade(ticker,signal,entry,sl,tgt)

            send_telegram_msg(
                f"📢 PAPER TRADE OPEN\n{ticker}\n{signal}\nEntry ₹{entry:.2f}\nSL ₹{sl:.2f}\nTarget ₹{tgt:.2f}\nQty {qty}"
            )

        except Exception as e:
            print("Error",ticker,e)

# ========= LOOP =========
print("🚀 BOT STARTED")

# ================================
# BACKGROUND BOT LOOP (Render Safe)
# ================================

def run_bot():
    print("🚀 BOT STARTED (Render Web Service)")
    send_telegram_msg("🤖 Paper trading Bot started")

    while True:
        try:
            if is_market_open():
                print("✅ Market OPEN → Scanning market")
                scan_and_alert()
            else:
                print("😴 Market closed")

            daily_reset()

        except Exception as e:
            print("❌ Bot loop error:", e)

        time.sleep(300)   # run every 5 minutes


# ================================
# START BACKGROUND THREAD
# ================================
Thread(target=run_bot, daemon=True).start()


# ================================
# FLASK ROUTE (Required by Render)
# ================================
@app.route("/")
def home():
    return "Stock Bot Running 🚀"


# ================================
# START WEB SERVER (Render needs this)
# ================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)