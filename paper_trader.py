# ===== PAPER TRADING ENGINE =====

capital = 100000
RISK_PER_TRADE = 0.01
RR = 2

open_trades = {}

def calculate_qty(entry, sl):
    global capital
    risk_amount = capital * RISK_PER_TRADE
    risk_per_share = abs(entry - sl)
    qty = int(risk_amount / risk_per_share)
    return max(qty,1)

def open_trade(ticker, direction, entry, sl, target):
    qty = calculate_qty(entry, sl)

    open_trades[ticker] = {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "target": target,
        "qty": qty
    }

    return qty

def check_exit(ticker, price):
    global capital

    if ticker not in open_trades:
        return None

    trade = open_trades[ticker]

    # LONG trade exit
    if trade["direction"] == "BUY":
        if price <= trade["sl"]:
            loss = (trade["entry"] - trade["sl"]) * trade["qty"]
            capital -= loss
            del open_trades[ticker]
            return f"❌ SL HIT {ticker} Loss ₹{round(loss,2)}\nCapital: ₹{round(capital,2)}"

        if price >= trade["target"]:
            profit = (trade["target"] - trade["entry"]) * trade["qty"]
            capital += profit
            del open_trades[ticker]
            return f"✅ TARGET HIT {ticker} Profit ₹{round(profit,2)}\nCapital: ₹{round(capital,2)}"

    # SHORT trade exit
    if trade["direction"] == "SELL":
        if price >= trade["sl"]:
            loss = (trade["sl"] - trade["entry"]) * trade["qty"]
            capital -= loss
            del open_trades[ticker]
            return f"❌ SL HIT {ticker} Loss ₹{round(loss,2)}\nCapital: ₹{round(capital,2)}"

        if price <= trade["target"]:
            profit = (trade["entry"] - trade["target"]) * trade["qty"]
            capital += profit
            del open_trades[ticker]
            return f"✅ TARGET HIT {ticker} Profit ₹{round(profit,2)}\nCapital: ₹{round(capital,2)}"

    return None