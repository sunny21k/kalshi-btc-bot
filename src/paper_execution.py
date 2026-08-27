import csv
import os
from datetime import datetime, timezone
from decimal import Decimal


TRADE_FILE = "data/paper_trades.csv"
FIELDNAMES = [
    "timestamp",
    "ticker",
    "side",
    "prediction",
    "entry_price",
    "model_probability",
    "edge",
    "contracts",
    "cost",
    "actual_result",
    "profit_loss",
    "correct",
]


def initialize_trade_file():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(TRADE_FILE) or os.path.getsize(TRADE_FILE) == 0:
        write_trade_rows([])
        return

    with open(TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    if reader.fieldnames == FIELDNAMES:
        return

    migrated_rows = [normalize_trade_row(row) for row in rows]
    write_trade_rows(migrated_rows)


def write_trade_rows(rows):
    with open(TRADE_FILE, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def normalize_trade_row(row):
    prediction = row.get("prediction") or row.get("signal") or ""
    side = row.get("side") or side_from_prediction(prediction)
    entry_price = normalize_price(row.get("entry_price") or row.get("yes_ask") or "")
    contracts = row.get("contracts", "")

    return {
        "timestamp": row.get("timestamp", ""),
        "ticker": row.get("ticker", ""),
        "side": side,
        "prediction": prediction,
        "entry_price": entry_price,
        "model_probability": row.get("model_probability", ""),
        "edge": row.get("edge", ""),
        "contracts": contracts,
        "cost": calculate_cost(entry_price, contracts),
        "actual_result": row.get("actual_result") or row.get("result") or "",
        "profit_loss": row.get("profit_loss") or row.get("pnl") or "",
        "correct": normalize_correct(row),
    }


def calculate_cost(entry_price, contracts):
    if entry_price in (None, "") or contracts in (None, ""):
        return ""

    return f"{Decimal(str(entry_price)) * int(contracts):.4f}"


def normalize_price(value):
    if value in (None, ""):
        return ""

    price = Decimal(str(value))
    if price > Decimal("1"):
        price = price / Decimal("100")

    return f"{price:.4f}"


def normalize_correct(row):
    if row.get("correct") not in (None, ""):
        return str(row["correct"])

    side = row.get("side") or side_from_prediction(row.get("prediction") or row.get("signal"))
    actual_result = row.get("actual_result") or row.get("result")
    if side in ["YES", "NO"] and actual_result in ["YES", "NO"]:
        return str(side == actual_result)

    return ""


def side_from_prediction(prediction):
    if prediction == "UP":
        return "YES"
    if prediction == "DOWN":
        return "NO"
    return ""


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

    entry_price = Decimal(str(entry_price))
    model_probability = Decimal(str(model_probability))
    edge = Decimal(str(edge))
    contracts = int(contracts)
    cost = entry_price * contracts

    with open(TRADE_FILE, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "side": side,
            "prediction": prediction,
            "entry_price": f"{entry_price:.4f}",
            "model_probability": f"{model_probability:.4f}",
            "edge": f"{edge:.4f}",
            "contracts": contracts,
            "cost": f"{cost:.4f}",
            "actual_result": "",
            "profit_loss": "",
            "correct": "",
        })

    return True


def update_paper_trade_results(get_market_result):
    initialize_trade_file()

    with open(TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    updated_count = 0

    for row in rows:
        if row.get("actual_result"):
            continue

        ticker = row.get("ticker")
        if not ticker:
            continue

        result = get_market_result(ticker)
        if result not in ["YES", "NO"]:
            continue

        row["actual_result"] = result
        row["profit_loss"] = calculate_profit_loss(row, result)
        row["correct"] = str(row.get("side") == result)
        updated_count += 1

    if updated_count:
        write_trade_rows(rows)

    return updated_count


def calculate_profit_loss(row, actual_result):
    side = row["side"]
    entry_price = Decimal(str(row["entry_price"]))
    contracts = Decimal(str(row["contracts"]))

    if side == actual_result:
        profit_loss = (Decimal("1.00") - entry_price) * contracts
    else:
        profit_loss = -entry_price * contracts

    return f"{profit_loss:.4f}"
