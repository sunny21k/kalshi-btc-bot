import csv
import os
from datetime import datetime, timezone

from outcome_tracker import get_market_result, prediction_was_correct


DATA_FILE = "data/market_data.csv"
RESULTS_FILE = "data/prediction_results.csv"


def initialize_results_file():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(RESULTS_FILE):
        return

    with open(RESULTS_FILE, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "timestamp",
            "ticker",
            "prediction",
            "actual_result",
            "correct",
        ])


def get_completed_predictions():
    if not os.path.exists(DATA_FILE):
        return {}

    predictions = {}

    with open(DATA_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            signal = row["signal"]
            ticker = row["ticker"]

            if signal not in ["UP", "DOWN"]:
                continue

            # Keep the latest prediction for each market
            predictions[ticker] = signal

    return predictions


def get_already_tracked():
    if not os.path.exists(RESULTS_FILE):
        return set()

    tracked = set()

    with open(RESULTS_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            tracked.add(row["ticker"])

    return tracked


def track_completed_markets():
    initialize_results_file()

    predictions = get_completed_predictions()
    already_tracked = get_already_tracked()

    new_results = 0

    for ticker, prediction in predictions.items():

        if ticker in already_tracked:
            continue

        try:
            result = get_market_result(ticker)
        except Exception as e:
            print(f"Could not check {ticker}: {e}")
            continue

        if result not in ["YES", "NO"]:
            continue

        correct = prediction_was_correct(prediction, result)

        with open(RESULTS_FILE, "a", newline="") as file:
            writer = csv.writer(file)

            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                ticker,
                prediction,
                result,
                correct,
            ])

        print(
            f"{ticker} | "
            f"Prediction: {prediction} | "
            f"Result: {result} | "
            f"{'CORRECT' if correct else 'INCORRECT'}"
        )

        new_results += 1

    return new_results


if __name__ == "__main__":
    print("Checking completed BTC markets...")
    print()

    count = track_completed_markets()

    print()
    print(f"New results recorded: {count}")
