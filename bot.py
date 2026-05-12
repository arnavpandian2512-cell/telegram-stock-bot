# ================================
# NIFTY50 ORB + VWAP + EMA + RISK CONTROL BOT
# FINAL PRO CLOUD VERSION 🚀
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
MAX_DAILY_LOSS_PCT = 2

# ========= FLASK =========
app = Flask(__name__)

# ========= TIME =========
IST = pytz.timezone("Asia/Kolkata")

# ========= CAPITAL =========
initial_capital = 100000
capital = initial_capital
RISK_PER_TRADE = 0.01

# ========= STATE =========
open_trades = {}
opening_range = {}
alerted_today = set()
orb_captured = set()

daily_trades = 0
daily_wins = 0
daily_losses = 0
daily_pnl = 0
daily_report_sent = False

# ========= TELEGRAM =========
def send_telegram_msg(message):
    print("📨 TELEGRAM:", message)
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print("Telegram Error:", e)

# ========= SYMBOLS =========
def get_nifty50_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    df = pd.read_csv(url)
    return [s + ".NS" for s in df['Symbol'].tolist()]

SYMBOLS = get_nifty50_symbols()

# ========= MARKET =========
def is_market_open():
    now = datetime.now(IST)
    return now.weekday() < 5 and dtime(9,15) <= now.time() <= dtime(15,30)

# ========= RISK CONTROL =========
def can_take_trade():
    drawdown = ((initial_capital - capital) / initial_capital) * 100
    if daily_trades >= MAX_TRADES_PER_DAY:
        print("⚠️ Max trades reached")
        return False
    if drawdown >= MAX_DAILY_LOSS_PCT:
        print("🚨 Max daily loss reached")
        return False
    return True

# ========= INDICATORS =========
def vwap(df):
    tp = (df['High']+df['Low']+df['Close'])/3
    return (tp*df['Volume']).cumsum().iloc[-1]/df['Volume'].cumsum().iloc[-1]

def ema(df, n=20):
    return df['Close'].ewm(span=n).mean().iloc[-1]

# ========= ORB =========
def capture_orb(ticker, df):
    now = datetime.now(IST).time()
    if ticker in orb_captured: return
    if dtime(9,15) <= now <= dtime(9,35):
        orb_df = df.between_time("09:15","09:30")
        if len(orb_df) < 5: return
        opening_range[ticker] = (
            float(orb_df["High"].max()),
            float(orb_df["Low"].min())
        )
        orb_captured.add(ticker)
        print("ORB captured:", ticker)

def check_orb(ticker, price):
    if ticker not in opening_range: return None
    high, low = opening_range[ticker]
    if price > high: return "BUY"
    if price < low: return "SELL"

# ========= TRADE ENGINE =========
def qty(entry, sl):
    risk = capital * RISK_PER_TRADE
    return max(int(risk / abs(entry-sl)),1)

def open_trade(ticker, direction, entry, sl, tgt):
    q = qty(entry, sl)
    open_trades[ticker] = {"dir":direction,"entry":entry,"sl":sl,"tgt":tgt,"qty":q}
    return q

def close_trade(ticker, price, reason):
    global capital, daily_trades, daily_wins, daily_losses, daily_pnl

    t = open_trades[ticker]
    q = t["qty"]

    pnl = (price-t["entry"])*q if t["dir"]=="BUY" else (t["entry"]-price)*q
    capital += pnl
    daily_trades += 1
    daily_pnl += pnl

    if pnl>0: daily_wins+=1
    else: daily_losses+=1

    del open_trades[ticker]

    send_telegram_msg(
        f"{reason} {ticker}\nPnL ₹{round(pnl,2)}\nCapital ₹{round(capital,2)}"
    )

def check_exit(ticker, price):
    if ticker not in open_trades: return
    t=open_trades[ticker]
    if t["dir"]=="BUY":
        if price<=t["sl"]: close_trade(ticker,t["sl"],"❌ SL HIT")
        elif price>=t["tgt"]: close_trade(ticker,t["tgt"],"✅ TARGET HIT")
    else:
        if price>=t["sl"]: close_trade(ticker,t["sl"],"❌ SL HIT")
        elif price<=t["tgt"]: close_trade(ticker,t["tgt"],"✅ TARGET HIT")

# ========= SCANNER =========
def scan():
    print("🔎 Scanning market...")
    for ticker in SYMBOLS:
        try:
            df=yf.download(ticker,period="1d",interval="1m",progress=False)
            if df.empty: continue
            if isinstance(df.columns,pd.MultiIndex):
                df.columns=df.columns.get_level_values(0)

            df=df[['Open','High','Low','Close','Volume']]
            capture_orb(ticker,df)

            price=float(df['Close'].iloc[-1])
            vw=vwap(df)
            e=ema(df)

            check_exit(ticker,price)
            signal=check_orb(ticker,price)

            if not signal or ticker in alerted_today: continue
            if not can_take_trade(): continue

            if signal=="BUY" and (price<vw or price<e): continue
            if signal=="SELL" and (price>vw or price>e): continue

            alerted_today.add(ticker)

            high,low=opening_range[ticker]
            risk=(high-low)*0.6

            if signal=="BUY":
                entry,sl,tgt=high,high-risk,high+risk*2
            else:
                entry,sl,tgt=low,low+risk,low-risk*2

            q=open_trade(ticker,signal,entry,sl,tgt)

            send_telegram_msg(
                f"📢 TRADE OPEN\n{ticker} {signal}\nEntry ₹{entry:.2f}\nSL ₹{sl:.2f}\nTarget ₹{tgt:.2f}\nQty {q}"
            )

        except Exception as e:
            print("Error:",ticker,e)

# ========= DAILY REPORT =========
def daily_report():
    global daily_report_sent
    now=datetime.now(IST)
    if now.hour==15 and now.minute>=35 and not daily_report_sent:
        winrate=(daily_wins/daily_trades*100) if daily_trades>0 else 0
        send_telegram_msg(
            f"📊 DAILY REPORT\nTrades:{daily_trades}\nWins:{daily_wins}\nLoss:{daily_losses}\nWinrate:{winrate:.1f}%\nPnL ₹{round(daily_pnl,2)}\nCapital ₹{round(capital,2)}"
        )
        daily_report_sent=True

# ========= BOT LOOP =========
def run_bot():
    print("🚀 BOT STARTED")
    send_telegram_msg("🤖 Bot LIVE on Render")

    while True:
        if is_market_open():
            scan()
        else:
            print("😴 Market closed")

        daily_report()
        time.sleep(600)

# ========= FLASK =========
@app.route("/")
def home():
    return "Stock Bot Running 🚀"

# ========= MAIN =========
if __name__ == "__main__":
    print("🚀 BOT LOOP STARTING WITH FLASK")

    Thread(target=run_bot, daemon=True).start()

    port=int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port,debug=False,use_reloader=False)