import csv
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal


SCALP_TRADE_FILE = "data/scalp_paper_trades.csv"
FIELDNAMES = [
    "timestamp",
    "opened_at",
    "closed_at",
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

    if not os.path.exists(SCALP_TRADE_FILE) or os.path.getsize(SCALP_TRADE_FILE) == 0:
        write_scalp_rows([])
        return

    with open(SCALP_TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    if reader.fieldnames == FIELDNAMES:
        return

    write_scalp_rows([normalize_scalp_row(row) for row in rows])


def write_scalp_rows(rows):
    with open(SCALP_TRADE_FILE, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def normalize_scalp_row(row):
    event = row.get("event", "")
    timestamp = row.get("timestamp", "")
    return {
        "timestamp": timestamp,
        "opened_at": row.get("opened_at") or (timestamp if event == "OPEN" else ""),
        "closed_at": row.get("closed_at") or (timestamp if event == "CLOSE" else ""),
        "trade_id": row.get("trade_id", ""),
        "event": event,
        "ticker": row.get("ticker", ""),
        "side": row.get("side", ""),
        "prediction": row.get("prediction", ""),
        "contracts": row.get("contracts", ""),
        "entry_price": row.get("entry_price", ""),
        "exit_price": row.get("exit_price", ""),
        "cost": row.get("cost", ""),
        "profit_loss": row.get("profit_loss", ""),
        "peak_profit": row.get("peak_profit", ""),
        "reason": row.get("reason", ""),
        "status": row.get("status", ""),
    }


def append_row(row):
    initialize_scalp_file()
    with open(SCALP_TRADE_FILE, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerow(row)


def open_position(*, ticker, side, prediction, entry_price, contracts, reason):
    trade_id = f"scalp-{uuid.uuid4()}"
    opened_at = datetime.now(timezone.utc).isoformat()
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
        "opened_at": opened_at,
    }
    append_row({
        "timestamp": opened_at,
        "opened_at": opened_at,
        "closed_at": "",
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
    closed_at = datetime.now(timezone.utc).isoformat()
    exit_price = Decimal(str(exit_price))
    profit_loss = Decimal(str(profit_loss))
    peak_profit = Decimal(str(peak_profit))
    append_row({
        "timestamp": closed_at,
        "opened_at": position.get("opened_at", ""),
        "closed_at": closed_at,
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
