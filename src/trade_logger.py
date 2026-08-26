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
            "signal",
            "model_probability",
            "yes_ask",
            "edge",
            "contracts",
            "entry_price",
            "result",
            "correct",
            "pnl",
        ])


def log_paper_trade(
    ticker,
    signal,
    model_probability,
    yes_ask,
    edge,
    contracts,
):
    initialize_trade_file()

    with open(TRADE_FILE, "a", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            ticker,
            signal,
            model_probability,
            yes_ask,
            edge,
            contracts,
            yes_ask,
            "",
            "",
            "",
        ])