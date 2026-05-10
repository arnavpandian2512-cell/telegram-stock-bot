# -*- coding: utf-8 -*-
import yfinance as yf
import requests
import pandas as pd
import time
from datetime import datetime, time as dtime

# ========= CONFIG =========
TEST_MODE = False
TELEGRAM_TOKEN = "8677296958:AAHVXYGWD1iriKts05lD8Tom65_u8sq7o1w"
CHAT_ID = "973055666"

# ========= PAPER TRADING =========
capital = 100000
RISK_PER_TRADE = 0.01
open_trades = {}

def calculate_qty(entry, sl):
    risk_amount = capital * RISK_PER_TRADE
    risk_per_share = abs(entry - sl)
    qty = int(risk_amount / risk_per_share)
    return max(qty,1)

def open_trade(ticker, direction, entry, sl, target):
    qty = calculate_qty(entry, sl)
    open_trades[ticker] = {"dir":direction,"entry":entry,"sl":sl,"target":target,"qty":qty}
    return qty

def check_exit(ticker, price):
    global capital
    if ticker not in open_trades:
        return None

    t = open_trades[ticker]

    # LONG
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

    # SHORT
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

# ========= TELEGRAM =========
def send_telegram_msg(message):
    if TEST_MODE:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url,json={"chat_id":CHAT_ID,"text":message})

# ========= NIFTY50 =========
def get_nifty50_symbols():
    url="https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    df=pd.read_csv(url)
    return [s+".NS" for s in df['Symbol'].tolist()]

SYMBOLS=get_nifty50_symbols()

# ========= MARKET HOURS =========
def is_market_open():
    now=datetime.now()
    if now.weekday()>=5: return False
    if now.hour<9 or (now.hour==9 and now.minute<15): return False
    if now.hour>15 or (now.hour==15 and now.minute>30): return False
    return True

opening_range={}
alerted_today=set()

# ========= INDICATORS =========
def calculate_vwap(df):
    tp=(df['High']+df['Low']+df['Close'])/3
    return (tp*df['Volume']).cumsum().iloc[-1]/df['Volume'].cumsum().iloc[-1]

def capture_opening_range(ticker, df):
    now=datetime.now().time()
    if dtime(9,15)<=now<=dtime(9,30):
        opening_range[ticker]=(df['High'].max(),df['Low'].min())

def check_orb_breakout(ticker, price):
    if ticker not in opening_range: return None
    high,low=opening_range[ticker]
    if price>high: return "BUY"
    if price<low: return "SELL"
    return None

# ========= MAIN SCANNER =========
def scan_and_alert():
    global capital

    for ticker in SYMBOLS:
        try:
            df=yf.download(ticker,period="1d",interval="1m",progress=False)
            if df.empty: continue

            capture_opening_range(ticker,df)

            price=df['Close'].iloc[-1]
            ema20=df['Close'].ewm(span=20).mean().iloc[-1]
            vwap=calculate_vwap(df)

            # check exits first
            exit_msg=check_exit(ticker,price)
            if exit_msg:
                send_telegram_msg(exit_msg)

            orb_signal=check_orb_breakout(ticker,price)
            if not orb_signal or ticker in alerted_today:
                continue

            if (orb_signal=="BUY" and price<vwap) or (orb_signal=="SELL" and price>vwap):
                continue

            alerted_today.add(ticker)

            high,low=opening_range[ticker]
            risk=(high-low)*0.6

            if orb_signal=="BUY":
                entry=high; sl=entry-risk; tgt=entry+(risk*2)
            else:
                entry=low; sl=entry+risk; tgt=entry-(risk*2)

            qty=open_trade(ticker,orb_signal,entry,sl,tgt)

            msg=(f"📢 PAPER TRADE OPEN\n{ticker}\n{orb_signal}\n"
                 f"Entry ₹{entry:.2f}\nSL ₹{sl:.2f}\nTarget ₹{tgt:.2f}\n"
                 f"Qty {qty}\nCapital ₹{round(capital,2)}")

            send_telegram_msg(msg)

        except Exception as e:
            print("Error",ticker,e)

# ========= LOOP =========
print("BOT STARTED 🚀")
send_telegram_msg("🤖 Paper Trading Bot Started")

while True:
    if is_market_open():
        scan_and_alert()
    else:
        print("Market closed")
    time.sleep(300)   # every 5 minutes