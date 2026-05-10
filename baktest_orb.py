import yfinance as yf
import pandas as pd
from datetime import time

# ================= CONFIG =================
SYMBOLS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS",
    "ICICIBANK.NS","INFY.NS","SBIN.NS"
]

TARGET   = 0.007   # 0.7%
STOPLOSS = 0.004   # 0.4%

results = []

# ================= INDICATORS =================
def calculate_vwap(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).cumsum() / df['Volume'].cumsum()

# ================= BACKTEST =================
for ticker in SYMBOLS:
    print("Testing", ticker)

    df = yf.download(ticker, period="60d", interval="5m", progress=False)

    # ⭐ FIX: flatten multi-level columns from Yahoo
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

        df.dropna(inplace=True)

    df['Time'] = df.index.time
    df['Date'] = df.index.date
    df['VWAP'] = calculate_vwap(df)
    df['EMA20'] = df['Close'].ewm(span=20).mean()

    # ---- Day by day testing ----
    for day in df['Date'].unique():

        day_df = df[df['Date']==day].copy()
        if len(day_df) < 50:
            continue

        # ===== Opening Range (9:15–9:45) =====
        orb_df = day_df.between_time("09:15","09:45")
        if len(orb_df) < 5:
            continue

        orb_high = float(orb_df['High'].max())
        orb_low  = float(orb_df['Low'].min())

        breakout_side = None
        trade_open = False
        entry_price = 0
        direction = None

        # ===== Intraday loop =====
        for i,row in day_df.iterrows():

            price = float(row['Close'])
            vwap  = float(row['VWAP'])
            ema   = float(row['EMA20'])

            # ---- Step 1: Detect breakout ----
            if breakout_side is None:
                if price > orb_high:
                    breakout_side = "BUY"
                elif price < orb_low:
                    breakout_side = "SELL"
                continue

            # ---- Step 2: Enter after confirmation ----
            if not trade_open:
                if breakout_side == "BUY" and price > vwap and price > ema:
                    trade_open = True
                    entry_price = price
                    direction = "BUY"
                    continue

                if breakout_side == "SELL" and price < vwap and price < ema:
                    trade_open = True
                    entry_price = price
                    direction = "SELL"
                    continue

            # ---- Step 3: Manage trade ----
            if trade_open:
                change = (price - entry_price) / entry_price
                if direction == "SELL":
                    change = -change

                if change >= TARGET:
                    results.append(1)
                    break

                if change <= -STOPLOSS:
                    results.append(0)
                    break

# ================= RESULTS =================
wins = sum(results)
trades = len(results)
winrate = (wins / trades * 100) if trades > 0 else 0

print("\n========== BACKTEST RESULT ==========")
print("Total Trades :", trades)
print("Winning Trades :", wins)
print("Win Rate :", round(winrate,2), "%")

if trades > 0:
    rr = TARGET/STOPLOSS
    expectancy = (winrate/100 * TARGET) - ((1-winrate/100) * STOPLOSS)
    print("Risk Reward :", round(rr,2))
    print("Expectancy per trade :", round(expectancy*100,3), "%")