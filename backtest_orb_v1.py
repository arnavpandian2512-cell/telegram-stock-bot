import yfinance as yf
import pandas as pd
import numpy as np
import pytz

stocks = ["RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS","SBIN.NS"]

capital = 100000
risk_per_trade = 0.01   # 1% risk
target_rr = 2           # 1:2 risk reward

total_trades = 0
winning_trades = 0
total_rr = []

IST = pytz.timezone("Asia/Kolkata")

def backtest(stock):
    global total_trades, winning_trades

    print(f"Testing {stock}")

    df = yf.download(stock, interval="5m", period="60d", progress=False)

    # ⭐ VERY IMPORTANT FIX — flatten yahoo multi-index columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df[['Open','High','Low','Close','Volume']]
    df.dropna(inplace=True)

    # convert timezone
    df.index = df.index.tz_convert(IST)

    df["Date"] = df.index.date
    df["Time"] = df.index.time

    days = df["Date"].unique()

    for day in days:
        day_df = df[df["Date"] == day]

        # market hours
        day_df = day_df.between_time("09:15","15:15")
        if len(day_df) < 20:
            continue

        # ORB = first 30 minutes (9:15 to 9:45)
        orb_df = day_df.between_time("09:15","09:45")

        if len(orb_df) < 3:
            continue

        orb_high = float(orb_df["High"].max())
        orb_low  = float(orb_df["Low"].min())
        orb_range = orb_high - orb_low
        
        if orb_range <= 0:
            continue

        risk = orb_range * 0.6
        target = risk * target_rr

        trade_taken = False

        # after 9:45 search breakout
        trade_df = day_df.between_time("09:50","14:30")

        for i,row in trade_df.iterrows():

            # LONG breakout
            if row["High"] > orb_high and not trade_taken:
                entry = orb_high
                sl = entry - risk
                tgt = entry + target
                trade_taken = True
                direction = "LONG"

            # SHORT breakout
            elif row["Low"] < orb_low and not trade_taken:
                entry = orb_low
                sl = entry + risk
                tgt = entry - target
                trade_taken = True
                direction = "SHORT"

            if not trade_taken:
                continue

            # after entry monitor exit
            after_entry = trade_df.loc[i:]

            for j,r in after_entry.iterrows():
                if direction == "LONG":
                    if r["Low"] <= sl:
                        total_trades += 1
                        total_rr.append(-1)
                        return
                    if r["High"] >= tgt:
                        total_trades += 1
                        winning_trades += 1
                        total_rr.append(target_rr)
                        return

                if direction == "SHORT":
                    if r["High"] >= sl:
                        total_trades += 1
                        total_rr.append(-1)
                        return
                    if r["Low"] <= tgt:
                        total_trades += 1
                        winning_trades += 1
                        total_rr.append(target_rr)
                        return

# run backtest
for s in stocks:
    backtest(s)

# ===== RESULT =====
print("\n========== BACKTEST RESULT ==========")
print("Total Trades :", total_trades)
print("Winning Trades :", winning_trades)

if total_trades > 0:
    winrate = winning_trades / total_trades * 100
    expectancy = np.mean(total_rr)

    print("Win Rate :", round(winrate,2),"%")
    print("Risk Reward :", target_rr)
    print("Expectancy per trade :", round(expectancy,3),"R")
else:
    print("Win Rate : 0%")