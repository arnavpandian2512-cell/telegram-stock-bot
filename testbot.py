
# -*- coding: utf-8 -*-
"""
Created on Sun May 10 00:24:53 2026

@author: Admin
"""
import yfinance as yf
import requests
import pandas as pd
import time
from datetime import datetime, time as dtime

# ========= CONFIG =========
TEST_MODE = False
TELEGRAM_TOKEN = "8677296958:AAHVXYGWD1iriKts05lD8Tom65_u8sq7o1w"
CHAT_ID = "973055666"

alerted_today = set()
opening_range = {}
gap_up_today = set()
gap_down_today = set()
gap_scan_done = False

# ========= TELEGRAM =========
def send_telegram_msg(message):
    if TEST_MODE:
        print("\n📢 TELEGRAM MESSAGE:\n", message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, json=payload)

# ========= NIFTY50 =========
def get_nifty50_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    df = pd.read_csv(url)
    return [s + ".NS" for s in df['Symbol'].tolist()]

SYMBOLS = get_nifty50_symbols()

# ========= MARKET HOURS =========
def is_market_open():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        return False
    if now.hour > 15 or (now.hour == 15 and now.minute > 30):
        return False
    return True

# ========= INDICATORS =========
def calculate_vwap(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).cumsum().iloc[-1] / df['Volume'].cumsum().iloc[-1]

def capture_opening_range(ticker, df):
    now = datetime.now().time()
    if dtime(9,15) <= now <= dtime(9,30):
        opening_range[ticker] = (df['High'].max(), df['Low'].min())

def check_orb_breakout(ticker, price):
    if ticker not in opening_range:
        return None
    high, low = opening_range[ticker]
    if price > high: return "BUY"
    if price < low: return "SELL"
    return None

# ========= GAP SCANNER =========
def gap_scanner():
    global gap_scan_done
    now = datetime.now().time()
    if gap_scan_done or not (dtime(9,15) <= now <= dtime(9,20)):
        return

    gap_up, gap_down = [], []
    for ticker in SYMBOLS:
        try:
            df = yf.download(ticker, period="2d", interval="1d", progress=False)
            if len(df) < 2: continue
            gap = (df['Open'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100
            if gap > 1:
                gap_up_today.add(ticker)
                gap_up.append(f"{ticker} (+{gap:.2f}%)")
            elif gap < -1:
                gap_down_today.add(ticker)
                gap_down.append(f"{ticker} ({gap:.2f}%)")
        except:
            pass

    msg = "<b>📊 GAP WATCHLIST</b>\n\n"
    msg += "🚀 Gap Up:\n" + "\n".join(gap_up[:10]) + "\n\n"
    msg += "🔻 Gap Down:\n" + "\n".join(gap_down[:10])
    send_telegram_msg(msg)
    gap_scan_done = True

# ========= SCORING =========
def calculate_score(ticker, orb_signal, price, ema20, vwap, volume_spike):
    score = 0
    if orb_signal: score += 2
    if orb_signal=="BUY" and price>vwap: score += 2
    if orb_signal=="SELL" and price<vwap: score += 2
    if orb_signal=="BUY" and price>ema20: score += 1
    if orb_signal=="SELL" and price<ema20: score += 1
    if volume_spike: score += 1
    if ticker in gap_up_today or ticker in gap_down_today: score += 1
    return score

def get_rating(score):
    if score>=6: return "⭐⭐⭐ STRONG"
    if score>=4: return "⭐⭐ MEDIUM"
    return "⭐ WEAK"

# ========= MAIN SCANNER =========
def scan_and_alert():
    for ticker in SYMBOLS:
        try:
            df = yf.download(ticker, period="1d", interval="1m", progress=False)
            if df.empty: continue

            capture_opening_range(ticker, df)

            price = df['Close'].iloc[-1]
            ema20 = df['Close'].ewm(span=20).mean().iloc[-1]
            vwap = calculate_vwap(df)

            avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
            volume_spike = df['Volume'].iloc[-1] > 2*avg_vol

            orb_signal = check_orb_breakout(ticker, price)
            score = calculate_score(ticker, orb_signal, price, ema20, vwap, volume_spike)
            rating = get_rating(score)

            if ticker not in alerted_today and orb_signal and score>=4:
                alerted_today.add(ticker)
                emoji = "🚀" if orb_signal=="BUY" else "🔻"
                msg = (f"{emoji} <b>{rating} SIGNAL</b>\n"
                       f"{ticker}\nSignal: {orb_signal}\nScore: {score}/7\nPrice: ₹{price:.2f}")
                send_telegram_msg(msg)

        except Exception as e:
            print("Error:", ticker, e)

# ========= TELEGRAM TEST =========
if __name__ == "__main__":
    send_telegram_msg("✅ Telegram bot connected successfully!")