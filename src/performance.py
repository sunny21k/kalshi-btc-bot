import csv
import os

from outcome_tracker import get_market_result, prediction_was_correct


DATA_FILE = "data/market_data.csv"


def load_predictions():
    if not os.path.exists(DATA_FILE):
        return {}

    predictions = {}

    with open(DATA_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            ticker = row["ticker"]
            signal = row["signal"]

            if signal not in ["UP", "DOWN"]:
                continue

            predictions[ticker] = signal

    return predictions


def main():
    predictions = load_predictions()

    if not predictions:
        print("No predictions found.")
        return

    total = 0
    correct = 0

    up_total = 0
    up_correct = 0

    down_total = 0
    down_correct = 0

    print()
    print("=" * 60)
    print("BTC 15M BOT PERFORMANCE")
    print("=" * 60)

    for ticker, signal in predictions.items():

        try:
            result = get_market_result(ticker)
        except Exception as e:
            print(f"Could not check {ticker}: {e}")
            continue

        if result not in ["YES", "NO"]:
            continue

        is_correct = prediction_was_correct(signal, result)

        total += 1

        if is_correct:
            correct += 1

        if signal == "UP":
            up_total += 1

            if is_correct:
                up_correct += 1

        elif signal == "DOWN":
            down_total += 1

            if is_correct:
                down_correct += 1

        print(
            f"{ticker} | "
            f"Prediction: {signal} | "
            f"Result: {result} | "
            f"{'CORRECT' if is_correct else 'INCORRECT'}"
        )

    print()
    print("-" * 60)

    accuracy = (correct / total) * 100 if total else 0

    print(f"Total Predictions: {total}")
    print(f"Correct: {correct}")
    print(f"Incorrect: {total - correct}")
    print(f"Accuracy: {accuracy:.2f}%")

    print()

    print(f"UP Predictions: {up_total}")

    if up_total:
        print(f"UP Accuracy: {(up_correct / up_total) * 100:.2f}%")
    else:
        print("UP Accuracy: N/A")

    print()

    print(f"DOWN Predictions: {down_total}")

    if down_total:
        print(f"DOWN Accuracy: {(down_correct / down_total) * 100:.2f}%")
    else:
        print("DOWN Accuracy: N/A")

    print("=" * 60)


if __name__ == "__main__":
    main()
