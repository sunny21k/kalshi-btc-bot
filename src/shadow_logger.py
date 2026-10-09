import csv
import os
from datetime import datetime, timezone


SHADOW_FILE = "data/shadow_signals.csv"
FIELDNAMES = [
    "timestamp",
    "ticker",
    "live_enabled",
    "decision",
    "side",
    "prediction",
    "entry_price",
    "strategy_name",
    "reason",
    "seconds_remaining",
    "price_difference",
]


def initialize_shadow_file():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(SHADOW_FILE) and os.path.getsize(SHADOW_FILE) > 0:
        return

    with open(SHADOW_FILE, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()


def log_shadow_signal(
    *,
    ticker,
    live_enabled,
    trade_signal,
    seconds_remaining,
):
    initialize_shadow_file()

    with open(SHADOW_FILE, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "live_enabled": live_enabled,
            "decision": trade_signal.get("decision", ""),
            "side": trade_signal.get("side", ""),
            "prediction": trade_signal.get("prediction", ""),
            "entry_price": trade_signal.get("entry_price") or "",
            "strategy_name": trade_signal.get("strategy_name", ""),
            "reason": trade_signal.get("reason", ""),
            "seconds_remaining": seconds_remaining or "",
            "price_difference": trade_signal.get("price_difference") or "",
        })
