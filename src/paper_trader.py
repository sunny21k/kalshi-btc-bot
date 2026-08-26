import csv
import os
from datetime import datetime, timezone


TRADES_FILE = "data/paper_trades.csv"


def initialize_trades_file():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(TRADES_FILE):
        return

    with open(TRADES_FILE, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "timestamp",
            "ticker",
            "prediction",
            "entry_price",
            "model_probability",
            "edge",
            "contracts",
            "cost",
            "actual_result",
            "profit_loss",
        ])


def record_paper_trade(
    ticker,
    prediction,
    entry_price,
    model_probability,
    edge,
    contracts=1,
):
    """
    Record a simulated trade at the exact moment
    the bot decides to BUY.

    No real money is used.
    """

    initialize_trades_file()

    cost = entry_price * contracts

    with open(TRADES_FILE, "a", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            ticker,
            prediction,
            entry_price,
            model_probability,
            edge,
            contracts,
            cost,
            "",
            "",
        ])

    print(
        f"PAPER TRADE: BUY {contracts} {prediction} "
        f"@ ${entry_price:.4f} "
        f"(cost=${cost:.4f})"
    )