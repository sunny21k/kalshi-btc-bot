import csv
import os
from decimal import Decimal

from outcome_tracker import prediction_was_correct


DATA_FILE = "data/market_data.csv"
PAPER_TRADES_FILE = "data/paper_trades.csv"
PREDICTION_RESULTS_FILE = "data/prediction_results.csv"


def decimal_or_zero(value):
    if value in (None, ""):
        return Decimal("0")

    return Decimal(str(value))


def percent(part, total):
    if not total:
        return None

    return Decimal(part) / Decimal(total) * Decimal("100")


def format_percent(value):
    if value is None:
        return "N/A"

    return f"{value:.2f}%"


def print_paper_trade_performance():
    if not os.path.exists(PAPER_TRADES_FILE):
        print("No paper trades found.")
        return

    total_trades = 0
    settled_trades = 0
    unsettled_trades = 0
    wins = 0
    total_invested = Decimal("0")
    total_profit_loss = Decimal("0")
    entry_price_total = Decimal("0")
    edge_total = Decimal("0")

    yes_total = 0
    yes_wins = 0
    yes_profit_loss = Decimal("0")
    yes_settled = 0

    no_total = 0
    no_wins = 0
    no_profit_loss = Decimal("0")
    no_settled = 0

    with open(PAPER_TRADES_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            total_trades += 1
            side = row.get("side", "")
            actual_result = row.get("actual_result", "")
            entry_price_total += decimal_or_zero(row.get("entry_price"))
            edge_total += decimal_or_zero(row.get("edge"))

            if side == "YES":
                yes_total += 1
            elif side == "NO":
                no_total += 1

            if actual_result not in ["YES", "NO"]:
                unsettled_trades += 1
                continue

            settled_trades += 1
            cost = decimal_or_zero(row.get("cost"))
            profit_loss = decimal_or_zero(row.get("profit_loss"))
            won = row.get("correct")
            if won in ("", None):
                won = side == actual_result
            else:
                won = won == "True"

            wins += int(won)
            total_invested += cost
            total_profit_loss += profit_loss

            if side == "YES":
                yes_settled += 1
                yes_wins += int(won)
                yes_profit_loss += profit_loss
            elif side == "NO":
                no_settled += 1
                no_wins += int(won)
                no_profit_loss += profit_loss

    print()
    print("=" * 60)
    print("PAPER TRADING PERFORMANCE")
    print("=" * 60)

    if not total_trades:
        print("No paper trades found.")
        return

    losses = settled_trades - wins
    win_rate = percent(wins, settled_trades)
    roi = (
        total_profit_loss / total_invested * 100
        if total_invested
        else Decimal("0")
    )
    average_entry_price = entry_price_total / total_trades
    average_edge = edge_total / total_trades

    print(f"Total Paper Trades: {total_trades}")
    print(f"Settled Trades: {settled_trades}")
    print(f"Unsettled Trades: {unsettled_trades}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    print(f"Win Rate: {format_percent(win_rate)}")
    print(f"Total Invested: ${total_invested:.4f}")
    print(f"Total Profit/Loss: ${total_profit_loss:.4f}")
    print(f"ROI: {roi:.2f}%")
    print(f"Average Entry Price: ${average_entry_price:.4f}")
    print(f"Average Edge: {average_edge * Decimal('100'):.2f}%")
    print()

    print(f"YES Trades: {yes_total}")
    print(f"YES Win Rate: {format_percent(percent(yes_wins, yes_settled))}")
    print(f"YES P/L: ${yes_profit_loss:.4f}")
    print()
    print(f"NO Trades: {no_total}")
    print(f"NO Win Rate: {format_percent(percent(no_wins, no_settled))}")
    print(f"NO P/L: ${no_profit_loss:.4f}")


def load_predictions():
    if os.path.exists(PREDICTION_RESULTS_FILE):
        predictions = []

        with open(PREDICTION_RESULTS_FILE, "r", newline="") as file:
            reader = csv.DictReader(file)

            for row in reader:
                if row.get("actual_result") in ["YES", "NO"]:
                    predictions.append(row)

        return predictions

    if not os.path.exists(DATA_FILE):
        return []

    predictions = {}

    with open(DATA_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            ticker = row["ticker"]
            signal = row["signal"]

            if signal not in ["UP", "DOWN"]:
                continue

            if ticker not in predictions:
                predictions[ticker] = {
                    "ticker": ticker,
                    "prediction": signal,
                    "actual_result": "",
                    "correct": "",
                }

    return list(predictions.values())


def print_prediction_performance():
    predictions = load_predictions()

    if not predictions:
        print("No settled predictions found.")
        return

    total = 0
    correct = 0

    up_total = 0
    up_correct = 0

    down_total = 0
    down_correct = 0

    print()
    print("=" * 60)
    print("MODEL PERFORMANCE")
    print("=" * 60)

    for row in predictions:
        prediction = row.get("prediction")
        actual_result = row.get("actual_result")

        if prediction not in ["UP", "DOWN"]:
            continue
        if actual_result not in ["YES", "NO"]:
            continue

        row_correct = row.get("correct")
        is_correct = (
            row_correct == "True"
            if row_correct not in (None, "")
            else prediction_was_correct(prediction, actual_result)
        )

        total += 1
        correct += int(is_correct)

        if prediction == "UP":
            up_total += 1
            up_correct += int(is_correct)
        elif prediction == "DOWN":
            down_total += 1
            down_correct += int(is_correct)

    print(f"Total Predictions: {total}")
    print(f"Correct: {correct}")
    print(f"Incorrect: {total - correct}")
    print(f"Accuracy: {format_percent(percent(correct, total))}")
    print()
    print(f"UP Predictions: {up_total}")
    print(f"UP Accuracy: {format_percent(percent(up_correct, up_total))}")
    print()
    print(f"DOWN Predictions: {down_total}")
    print(f"DOWN Accuracy: {format_percent(percent(down_correct, down_total))}")
    print("=" * 60)


def main():
    print_paper_trade_performance()
    print_prediction_performance()


if __name__ == "__main__":
    main()
