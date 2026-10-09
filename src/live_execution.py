import csv
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from kalshi_api import create_order


LIVE_TRADE_FILE = "data/live_trades.csv"
MAX_CONTRACTS = 1
MAX_TRADE_COST = Decimal("1.00")
FIELDNAMES = [
    "timestamp",
    "ticker",
    "side",
    "prediction",
    "entry_price",
    "contracts",
    "max_cost",
    "order_side",
    "order_price",
    "client_order_id",
    "status",
    "order_id",
    "actual_result",
    "profit_loss",
    "correct",
    "response",
    "error",
]


def initialize_live_trade_file():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(LIVE_TRADE_FILE) or os.path.getsize(LIVE_TRADE_FILE) == 0:
        write_live_trade_rows([])
        return

    with open(LIVE_TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    if reader.fieldnames == FIELDNAMES:
        return

    migrated_rows = [
        {field: row.get(field, "") for field in FIELDNAMES}
        for row in rows
    ]
    write_live_trade_rows(migrated_rows)


def write_live_trade_rows(rows):
    with open(LIVE_TRADE_FILE, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def has_live_traded(ticker):
    initialize_live_trade_file()

    with open(LIVE_TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row["ticker"] == ticker and not row.get("error"):
                return True

    return False


def order_details_for_side(side, entry_price):
    entry_price = Decimal(str(entry_price))

    if side == "YES":
        return "bid", entry_price

    if side == "NO":
        return "ask", Decimal("1.00") - entry_price

    raise ValueError(f"Unsupported live trade side: {side}")


def extract_order_id(response):
    order = response.get("order", response)
    return str(order.get("order_id") or order.get("id") or "")


def extract_order_status(response):
    order = response.get("order", response)
    return str(order.get("status") or "")


def append_live_trade_row(row):
    initialize_live_trade_file()

    with open(LIVE_TRADE_FILE, "a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writerow(row)


def place_live_trade(
    ticker,
    side,
    prediction,
    entry_price,
    *,
    contracts=1,
    exchange_index=None,
    create_order_fn=create_order,
):
    initialize_live_trade_file()

    if has_live_traded(ticker):
        return False

    contracts = int(contracts)
    if contracts != MAX_CONTRACTS:
        raise ValueError("Live trading is limited to exactly 1 contract per trade")

    entry_price = Decimal(str(entry_price))
    max_cost = entry_price * contracts
    if max_cost > MAX_TRADE_COST:
        raise ValueError("Live trade cost exceeds $1.00 max")

    order_side, order_price = order_details_for_side(side, entry_price)
    client_order_id = f"btc15m-live-{uuid.uuid4()}"

    base_row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "side": side,
        "prediction": prediction,
        "entry_price": f"{entry_price:.4f}",
        "contracts": contracts,
        "max_cost": f"{max_cost:.4f}",
        "order_side": order_side,
        "order_price": f"{order_price:.4f}",
        "client_order_id": client_order_id,
        "status": "",
        "order_id": "",
        "actual_result": "",
        "profit_loss": "",
        "correct": "",
        "response": "",
        "error": "",
    }

    try:
        response = create_order_fn(
            ticker,
            side=order_side,
            count=contracts,
            price=order_price,
            client_order_id=client_order_id,
            time_in_force="immediate_or_cancel",
            exchange_index=exchange_index,
        )
    except Exception as exc:
        failed_row = dict(base_row)
        failed_row["status"] = "ERROR"
        failed_row["error"] = str(exc)
        append_live_trade_row(failed_row)
        raise

    completed_row = dict(base_row)
    completed_row["status"] = extract_order_status(response)
    completed_row["order_id"] = extract_order_id(response)
    completed_row["response"] = json.dumps(response, sort_keys=True)
    append_live_trade_row(completed_row)

    return True


def update_live_trade_results(get_market_result):
    initialize_live_trade_file()

    with open(LIVE_TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    updated_count = 0

    for row in rows:
        if row.get("actual_result") or row.get("error"):
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
        write_live_trade_rows(rows)

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
