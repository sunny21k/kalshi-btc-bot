import csv
import os
from datetime import datetime, timezone


DATA_FILE = "data/market_data.csv"


def initialize_data_file():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "timestamp",
            "ticker",
            "btc_price",
            "btc_change",
            "signal",
            "model_probability",
            "yes_bid",
            "yes_ask",
            "spread",
            "edge",
            "seconds_remaining",
        ])


def log_market_data(
    ticker,
    btc_price,
    btc_change,
    signal,
    model_probability,
    yes_bid,
    yes_ask,
    spread,
    edge,
    seconds_remaining,
):

    initialize_data_file()

    with open(DATA_FILE, "a", newline="") as file:

        writer = csv.writer(file)

        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            ticker,
            btc_price,
            btc_change,
            signal,
            model_probability,
            yes_bid,
            yes_ask,
            spread,
            edge,
            seconds_remaining,
        ])