import csv
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal


SCALP_TRADE_FILE = "data/scalp_paper_trades.csv"
FIELDNAMES = [
    "timestamp",
    "trade_id",
    "event",
    "ticker",
    "side",
    "prediction",
    "contracts",
    "entry_price",
    "exit_price",
    "cost",
    "profit_loss",
    "peak_profit",
    "reason",
    "status",
]


def initialize_scalp_file():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(SCALP_TRADE_FILE) and os.path.getsize(SCALP_TRADE_FILE) > 0:
        return

    with open(SCALP_TRADE_FILE, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()


def append_row(row):
    initialize_scalp_file()
    with open(SCALP_TRADE_FILE, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerow(row)


def open_position(*, ticker, side, prediction, entry_price, contracts, reason):
    trade_id = f"scalp-{uuid.uuid4()}"
    entry_price = Decimal(str(entry_price))
    contracts = int(contracts)
    cost = entry_price * contracts
    position = {
        "trade_id": trade_id,
        "ticker": ticker,
        "side": side,
        "prediction": prediction,
        "entry_price": entry_price,
        "contracts": contracts,
        "cost": cost,
        "peak_profit": Decimal("0"),
    }
    append_row({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trade_id": trade_id,
        "event": "OPEN",
        "ticker": ticker,
        "side": side,
        "prediction": prediction,
        "contracts": contracts,
        "entry_price": f"{entry_price:.4f}",
        "exit_price": "",
        "cost": f"{cost:.4f}",
        "profit_loss": "",
        "peak_profit": "0.0000",
        "reason": reason,
        "status": "OPEN",
    })
    return position


def close_position(position, *, exit_price, profit_loss, peak_profit, reason):
    exit_price = Decimal(str(exit_price))
    profit_loss = Decimal(str(profit_loss))
    peak_profit = Decimal(str(peak_profit))
    append_row({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trade_id": position["trade_id"],
        "event": "CLOSE",
        "ticker": position["ticker"],
        "side": position["side"],
        "prediction": position["prediction"],
        "contracts": position["contracts"],
        "entry_price": f"{Decimal(str(position['entry_price'])):.4f}",
        "exit_price": f"{exit_price:.4f}",
        "cost": f"{Decimal(str(position['cost'])):.4f}",
        "profit_loss": f"{profit_loss:.4f}",
        "peak_profit": f"{peak_profit:.4f}",
        "reason": reason,
        "status": "CLOSED",
    })
