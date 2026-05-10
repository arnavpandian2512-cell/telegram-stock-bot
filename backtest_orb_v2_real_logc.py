import yfinance as yf
import pandas as pd
import numpy as np
import pytz
import matplotlib.pyplot as plt

# ========= SETTINGS =========
#stocks = ["RELIANCE.NS","TCS.NS","HDFCBANK.NS","ICICIBANK.NS","INFY.NS","SBIN.NS"]

def get_nifty50():
    url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    df = pd.read_csv(url)
    return [s + ".NS" for s in df["Symbol"].tolist()]

stocks = get_nifty50()

START_CAPITAL = 100000
RISK_PER_TRADE = 0.01     # risk 1% per trade
RR = 2                    # risk reward 1:2

capital = START_CAPITAL
equity_curve = []

total_trades = 0
winning_trades = 0

IST = pytz.timezone("Asia/Kolkata")

# ========= BACKTEST FUNCTION =========
def backtest(stock):
    global total_trades, winning_trades, capital

    print(f"Testing {stock}")

    df = yf.download(stock, interval="5m", period="60d", progress=False)

    # Fix Yahoo multi-index columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[['Open','High','Low','Close','Volume']]
    df.dropna(inplace=True)

    # Convert timezone
    df.index = df.index.tz_convert(IST)

    df["Date"] = df.index.date
    days = df["Date"].unique()

    for day in days:
        day_df = df[df["Date"] == day]
        day_df = day_df.between_time("09:15","15:15")

        if len(day_df) < 20:
            continue

        # ===== Opening Range 9:15–9:45 =====
        orb_df = day_df.between_time("09:15","09:45")
        if len(orb_df) < 3:
            continue

        orb_high = orb_df["High"].max()
        orb_low  = orb_df["Low"].min()
        orb_range = orb_high - orb_low

        if orb_range <= 0:
            continue

        risk_points = orb_range * 0.6
        target_points = risk_points * RR

        trade_taken = False

        # ===== Look for breakout after 9:50 =====
        trade_df = day_df.between_time("09:50","14:30")

        for i,row in trade_df.iterrows():

            # LONG breakout
            if row["High"] > orb_high and not trade_taken:
                entry = orb_high
                sl = entry - risk_points
                tgt = entry + target_points
                trade_taken = True
                direction = "LONG"

            # SHORT breakout
            elif row["Low"] < orb_low and not trade_taken:
                entry = orb_low
                sl = entry + risk_points
                tgt = entry - target_points
                trade_taken = True
                direction = "SHORT"

            if not trade_taken:
                continue

            # ===== Monitor exit after entry =====
            after_entry = trade_df.loc[i:]

            for j,r in after_entry.iterrows():

                risk_amount = capital * RISK_PER_TRADE

                # LONG trade exits
                if direction == "LONG":
                    if r["Low"] <= sl:
                        capital -= risk_amount
                        equity_curve.append(capital)
                        total_trades += 1
                        return

                    if r["High"] >= tgt:
                        capital += risk_amount * RR
                        winning_trades += 1
                        equity_curve.append(capital)
                        total_trades += 1
                        return

                # SHORT trade exits
                if direction == "SHORT":
                    if r["High"] >= sl:
                        capital -= risk_amount
                        equity_curve.append(capital)
                        total_trades += 1
                        return

                    if r["Low"] <= tgt:
                        capital += risk_amount * RR
                        winning_trades += 1
                        equity_curve.append(capital)
                        total_trades += 1
                        return

# ========= RUN BACKTEST =========
for s in stocks:
    backtest(s)

# ========= FINAL RESULT =========
print("\n========== BACKTEST RESULT ==========")
print("Total Trades :", total_trades)
print("Winning Trades :", winning_trades)

if total_trades > 0:
    winrate = winning_trades / total_trades * 100
    profit = capital - START_CAPITAL
    roi = (profit / START_CAPITAL) * 100

    print("Win Rate :", round(winrate,2), "%")
    print("\nStarting Capital :", START_CAPITAL)
    print("Ending Capital :", round(capital,2))
    print("Net Profit :", round(profit,2))
    print("ROI :", round(roi,2), "%")
else:
    print("No trades triggered")
    
    
# ========= DRAWDOWN & EQUITY =========

equity = pd.Series(equity_curve)

# running peak capital
running_max = equity.cummax()

# drawdown %
drawdown = (equity - running_max) / running_max * 100

max_dd = drawdown.min()

print("\n========== RISK METRICS ==========")
print("Max Drawdown :", round(max_dd,2), "%")

# ========= PLOT EQUITY CURVE =========
plt.figure(figsize=(10,5))
plt.plot(equity_curve)
plt.title("Equity Curve")
plt.xlabel("Trades")
plt.ylabel("Capital")
plt.grid()
plt.show()