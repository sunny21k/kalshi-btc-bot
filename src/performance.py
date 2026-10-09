import csv
import os
from decimal import Decimal

from live_execution import LIVE_TRADE_FILE
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


def entry_price_bucket(entry_price):
    price = Decimal(str(entry_price))
    if price < Decimal("0.80"):
        return "75-80%"
    if price < Decimal("0.85"):
        return "80-85%"
    if price < Decimal("0.90"):
        return "85-90%"
    return "90-92%"


def time_bucket(seconds_remaining):
    if seconds_remaining in (None, ""):
        return "unknown"

    minutes = Decimal(str(seconds_remaining)) / Decimal("60")
    if minutes > Decimal("5"):
        return "6-5 min"
    if minutes > Decimal("4"):
        return "5-4 min"
    if minutes > Decimal("3"):
        return "4-3 min"
    if minutes > Decimal("2"):
        return "3-2 min"
    if minutes > Decimal("1"):
        return "2-1 min"
    if minutes > Decimal("0.5"):
        return "1-0.5 min"
    return "0.5-0 min"


def add_bucket_stats(stats, key, won, profit_loss):
    item = stats.setdefault(
        key,
        {"total": 0, "settled": 0, "wins": 0, "profit_loss": Decimal("0")},
    )
    item["total"] += 1
    if won is not None:
        item["settled"] += 1
        item["wins"] += int(won)
        item["profit_loss"] += profit_loss


def print_bucket_stats(title, stats):
    if not stats:
        return

    print()
    print(title)
    for key in sorted(stats):
        item = stats[key]
        print(
            f"{key}: {item['total']} trades | "
            f"Win Rate: {format_percent(percent(item['wins'], item['settled']))} | "
            f"P/L: ${item['profit_loss']:.4f}"
        )


def print_trade_performance(
    *,
    file_path,
    title,
    total_label,
    no_trades_message,
    cost_field,
    include_edge,
):
    if not os.path.exists(file_path):
        print(no_trades_message)
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
    strategy_stats = {}
    entry_stats = {}
    time_stats = {}

    with open(file_path, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("error"):
                continue

            total_trades += 1
            side = row.get("side", "")
            actual_result = row.get("actual_result", "")
            entry_price = decimal_or_zero(row.get("entry_price"))
            entry_price_total += entry_price
            if include_edge:
                edge_total += decimal_or_zero(row.get("edge"))

            if side == "YES":
                yes_total += 1
            elif side == "NO":
                no_total += 1

            if actual_result not in ["YES", "NO"]:
                unsettled_trades += 1
                add_bucket_stats(
                    strategy_stats,
                    row.get("strategy_name") or "unknown",
                    None,
                    Decimal("0"),
                )
                add_bucket_stats(
                    entry_stats,
                    entry_price_bucket(entry_price),
                    None,
                    Decimal("0"),
                )
                add_bucket_stats(
                    time_stats,
                    time_bucket(row.get("seconds_remaining")),
                    None,
                    Decimal("0"),
                )
                continue

            settled_trades += 1
            if row.get("filled_count") not in (None, ""):
                cost = entry_price * decimal_or_zero(row.get("filled_count"))
            else:
                cost = decimal_or_zero(row.get(cost_field))
            profit_loss = decimal_or_zero(row.get("profit_loss"))
            won = row.get("correct")
            if won in ("", None):
                won = side == actual_result
            else:
                won = won == "True"

            wins += int(won)
            total_invested += cost
            total_profit_loss += profit_loss
            add_bucket_stats(
                strategy_stats,
                row.get("strategy_name") or "unknown",
                won,
                profit_loss,
            )
            add_bucket_stats(
                entry_stats,
                entry_price_bucket(entry_price),
                won,
                profit_loss,
            )
            add_bucket_stats(
                time_stats,
                time_bucket(row.get("seconds_remaining")),
                won,
                profit_loss,
            )

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
    print(title)
    print("=" * 60)

    if not total_trades:
        print(no_trades_message)
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

    print(f"{total_label}: {total_trades}")
    print(f"Settled Trades: {settled_trades}")
    print(f"Unsettled Trades: {unsettled_trades}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    print(f"Win Rate: {format_percent(win_rate)}")
    print(f"Total Invested: ${total_invested:.4f}")
    print(f"Total Profit/Loss: ${total_profit_loss:.4f}")
    print(f"ROI: {roi:.2f}%")
    print(f"Average Entry Price: ${average_entry_price:.4f}")
    if include_edge:
        print(f"Average Edge: {average_edge * Decimal('100'):.2f}%")
    print()

    print(f"YES Trades: {yes_total}")
    print(f"YES Win Rate: {format_percent(percent(yes_wins, yes_settled))}")
    print(f"YES P/L: ${yes_profit_loss:.4f}")
    print()
    print(f"NO Trades: {no_total}")
    print(f"NO Win Rate: {format_percent(percent(no_wins, no_settled))}")
    print(f"NO P/L: ${no_profit_loss:.4f}")
    print_bucket_stats("By Strategy", strategy_stats)
    print_bucket_stats("By Entry Price", entry_stats)
    print_bucket_stats("By Time Remaining", time_stats)


def print_paper_trade_performance():
    print_trade_performance(
        file_path=PAPER_TRADES_FILE,
        title="PAPER TRADING PERFORMANCE",
        total_label="Total Paper Trades",
        no_trades_message="No paper trades found.",
        cost_field="cost",
        include_edge=True,
    )


def print_live_trade_performance():
    print_trade_performance(
        file_path=LIVE_TRADE_FILE,
        title="LIVE TRADING PERFORMANCE",
        total_label="Total Live Trades",
        no_trades_message="No live trades found.",
        cost_field="max_cost",
        include_edge=False,
    )


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
    print_live_trade_performance()
    print_prediction_performance()


if __name__ == "__main__":
    main()
