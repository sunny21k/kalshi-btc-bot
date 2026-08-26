import csv
import os
from datetime import datetime, timezone


TRADE_FILE = "data/paper_trades.csv"


def initialize_trade_file():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(TRADE_FILE):
        return

    with open(TRADE_FILE, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
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
        ])


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

    cost = entry_price * contracts

    with open(TRADE_FILE, "a", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            ticker,
            side,
            prediction,
            entry_price,
            model_probability,
            edge,
            contracts,
            cost,
            "",
            "",
        ])

    return True
