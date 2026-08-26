import csv
import os
from datetime import datetime, timezone
from decimal import Decimal


TRADE_FILE = "data/paper_trades.csv"
FIELDNAMES = [
    "timestamp",
    "ticker",
    "side",
    "prediction",
    "entry_price",
    "model_probability",
    "edge",
    "contracts",
    "cost",
    "result",
    "profit_loss",
]


def initialize_trade_file():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(TRADE_FILE) or os.path.getsize(TRADE_FILE) == 0:
        write_trade_rows([])
        return

    with open(TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    if reader.fieldnames == FIELDNAMES:
        return

    migrated_rows = [normalize_trade_row(row) for row in rows]
    write_trade_rows(migrated_rows)


def write_trade_rows(rows):
    with open(TRADE_FILE, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def normalize_trade_row(row):
    prediction = row.get("prediction") or row.get("signal") or ""
    side = row.get("side") or side_from_prediction(prediction)

    return {
        "timestamp": row.get("timestamp", ""),
        "ticker": row.get("ticker", ""),
        "side": side,
        "prediction": prediction,
        "entry_price": row.get("entry_price") or row.get("yes_ask") or "",
        "model_probability": row.get("model_probability", ""),
        "edge": row.get("edge", ""),
        "contracts": row.get("contracts", ""),
        "cost": row.get("cost", ""),
        "result": row.get("result") or row.get("actual_result") or "",
        "profit_loss": row.get("profit_loss") or row.get("pnl") or "",
    }


def side_from_prediction(prediction):
    if prediction == "UP":
        return "YES"
    if prediction == "DOWN":
        return "NO"
    return ""


def has_traded(ticker):
    initialize_trade_file()

    with open(TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row["ticker"] == ticker:
                return True

    return False


def record_paper_trade(
    ticker,
    side,
    prediction,
    entry_price,
    model_probability,
    edge,
    contracts=1,
):
    initialize_trade_file()

    if has_traded(ticker):
        return False

    entry_price = Decimal(str(entry_price))
    model_probability = Decimal(str(model_probability))
    edge = Decimal(str(edge))
    contracts = int(contracts)
    cost = entry_price * contracts

    with open(TRADE_FILE, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "side": side,
            "prediction": prediction,
            "entry_price": f"{entry_price:.4f}",
            "model_probability": f"{model_probability:.4f}",
            "edge": f"{edge:.4f}",
            "contracts": contracts,
            "cost": f"{cost:.4f}",
            "result": "",
            "profit_loss": "",
        })

    return True
