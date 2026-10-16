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
MAX_LIVE_TRADES_PER_DAY = 30
MAX_DAILY_LIVE_LOSS = Decimal(os.getenv("KALSHI_MAX_DAILY_LIVE_LOSS", "10"))
FIELDNAMES = [
    "timestamp",
    "trade_id",
    "ticker",
    "side",
    "prediction",
    "entry_price",
    "strategy_name",
    "seconds_remaining",
    "contracts",
    "submitted_count",
    "filled_count",
    "fill_status",
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
        normalize_live_trade_row(row)
        for row in rows
    ]
    write_live_trade_rows(migrated_rows)


def normalize_live_trade_row(row):
    normalized = {field: row.get(field, "") for field in FIELDNAMES}
    if not normalized["trade_id"]:
        normalized["trade_id"] = legacy_trade_id("live", row)
    return normalized


def legacy_trade_id(prefix, row):
    source = "|".join([
        row.get("timestamp", ""),
        row.get("ticker", ""),
        row.get("side", ""),
        row.get("client_order_id", ""),
    ])
    return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, source)}"


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
            if row["ticker"] == ticker:
                return True

    return False


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def live_rows_for_day(day, *, now=None):
    initialize_live_trade_file()

    rows = []
    with open(LIVE_TRADE_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("error") or not row.get("timestamp"):
                continue

            timestamp = parse_timestamp(row["timestamp"])
            if timestamp.date() == day:
                rows.append(row)

    return rows


def live_trade_count_today(*, now=None):
    now = now or datetime.now(timezone.utc)
    return len(live_rows_for_day(now.date(), now=now))


def realized_live_profit_loss_today(*, now=None):
    now = now or datetime.now(timezone.utc)
    total = Decimal("0")

    for row in live_rows_for_day(now.date(), now=now):
        profit_loss = row.get("profit_loss")
        if profit_loss not in (None, ""):
            total += Decimal(str(profit_loss))

    return total


def validate_live_risk_limits(*, now=None):
    now = now or datetime.now(timezone.utc)

    if live_trade_count_today(now=now) >= MAX_LIVE_TRADES_PER_DAY:
        raise RuntimeError("Daily live trade limit reached")

    if realized_live_profit_loss_today(now=now) <= -MAX_DAILY_LIVE_LOSS:
        raise RuntimeError("Daily live loss limit reached")


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


def extract_count(response, *keys, default=""):
    order = response.get("order", response)
    for key in keys:
        value = order.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def normalize_filled_count(response, submitted_count):
    filled_count = extract_count(
        response,
        "filled_count",
        "fill_count",
        "filled_contracts",
        "filled",
    )
    if filled_count:
        return filled_count

    status = extract_order_status(response).lower()
    if status in ("executed", "filled"):
        return str(submitted_count)

    return "0"


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
    strategy_name="",
    seconds_remaining="",
    contracts=1,
    exchange_index=None,
    create_order_fn=create_order,
):
    initialize_live_trade_file()

    if has_live_traded(ticker):
        return False

    validate_live_risk_limits()

    contracts = int(contracts)
    if contracts != MAX_CONTRACTS:
        raise ValueError("Live trading is limited to exactly 1 contract per trade")

    entry_price = Decimal(str(entry_price))
    max_cost = entry_price * contracts
    if max_cost > MAX_TRADE_COST:
        raise ValueError("Live trade cost exceeds $1.00 max")

    order_side, order_price = order_details_for_side(side, entry_price)
    trade_id = f"live-{uuid.uuid4()}"
    client_order_id = f"btc15m-{trade_id}"

    base_row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trade_id": trade_id,
        "ticker": ticker,
        "side": side,
        "prediction": prediction,
        "entry_price": f"{entry_price:.4f}",
        "strategy_name": strategy_name,
        "seconds_remaining": (
            f"{Decimal(str(seconds_remaining)):.4f}"
            if seconds_remaining not in (None, "")
            else ""
        ),
        "contracts": contracts,
        "submitted_count": contracts,
        "filled_count": "",
        "fill_status": "",
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
    completed_row["filled_count"] = normalize_filled_count(response, contracts)
    completed_row["fill_status"] = (
        "FILLED"
        if Decimal(str(completed_row["filled_count"])) >= Decimal(str(contracts))
        else "PARTIAL_OR_UNFILLED"
    )
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
    contracts = Decimal(str(row.get("filled_count") or row["contracts"]))

    if side == actual_result:
        profit_loss = (Decimal("1.00") - entry_price) * contracts
    else:
        profit_loss = -entry_price * contracts

    return f"{profit_loss:.4f}"
