import csv
import os
from datetime import datetime, timezone


DATA_FILE = "data/market_data.csv"


def initialize_data_file(data_file=None):
    data_file = data_file or DATA_FILE
    os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)

    if os.path.exists(data_file):
        return

    with open(data_file, "w", newline="") as file:
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
    *,
    data_file=None,
):

    data_file = data_file or DATA_FILE
    initialize_data_file(data_file)

    with open(data_file, "a", newline="") as file:

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
