import csv
import fcntl
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trade_sizing import contracts_for_budget as size_contracts


TRADE_FILE = "data/paper_trades.csv"
DUAL_TRADE_FILE = "data/dual_paper_trades.csv"
PAPER_TRADE_BUDGET = Decimal("100")
FIELDNAMES = [
    "timestamp",
    "trade_id",
    "ticker",
    "side",
    "prediction",
    "entry_price",
    "model_probability",
    "edge",
    "strategy_name",
    "seconds_remaining",
    "contracts",
    "cost",
    "actual_result",
    "profit_loss",
    "correct",
]


@contextmanager
def paper_ledger_lock(trade_file=None):
    trade_file = trade_file or TRADE_FILE
    Path(trade_file).parent.mkdir(parents=True, exist_ok=True)
    with open(f"{trade_file}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def initialize_trade_file(trade_file=None):
    trade_file = trade_file or TRADE_FILE
    with paper_ledger_lock(trade_file):
        _initialize_trade_file(trade_file)


def _initialize_trade_file(trade_file):
    os.makedirs(os.path.dirname(trade_file) or ".", exist_ok=True)

    if not os.path.exists(trade_file) or os.path.getsize(trade_file) == 0:
        _write_trade_rows([], trade_file)
        return

    with open(trade_file, "r", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    if reader.fieldnames == FIELDNAMES and all(row.get("trade_id") for row in rows):
        return

    migrated_rows = [normalize_trade_row(row) for row in rows]
    _write_trade_rows(migrated_rows, trade_file)


def write_trade_rows(rows, trade_file=None):
    trade_file = trade_file or TRADE_FILE
    with paper_ledger_lock(trade_file):
        _write_trade_rows(rows, trade_file)


def _write_trade_rows(rows, trade_file):
    fd, temporary_path = tempfile.mkstemp(dir=Path(trade_file).parent, prefix=".paper-trades-")
    try:
        with os.fdopen(fd, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, trade_file)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def read_trade_rows(trade_file=None):
    trade_file = trade_file or TRADE_FILE
    with paper_ledger_lock(trade_file):
        _initialize_trade_file(trade_file)
        with open(trade_file, "r", newline="") as file:
            return list(csv.DictReader(file))


def normalize_trade_row(row):
    prediction = row.get("prediction") or row.get("signal") or ""
    side = row.get("side") or side_from_prediction(prediction)
    entry_price = normalize_price(row.get("entry_price") or row.get("yes_ask") or "")
    contracts = row.get("contracts", "")

    return {
        "timestamp": row.get("timestamp", ""),
        "trade_id": row.get("trade_id") or legacy_trade_id("paper", row),
        "ticker": row.get("ticker", ""),
        "side": side,
        "prediction": prediction,
        "entry_price": entry_price,
        "model_probability": row.get("model_probability", ""),
        "edge": row.get("edge", ""),
        "strategy_name": row.get("strategy_name", ""),
        "seconds_remaining": row.get("seconds_remaining", ""),
        "contracts": contracts,
        "cost": calculate_cost(entry_price, contracts),
        "actual_result": row.get("actual_result") or row.get("result") or "",
        "profit_loss": row.get("profit_loss") or row.get("pnl") or "",
        "correct": normalize_correct(row),
    }


def legacy_trade_id(prefix, row):
    source = "|".join([
        row.get("timestamp", ""),
        row.get("ticker", ""),
        row.get("side", ""),
        row.get("prediction", ""),
    ])
    return f"{prefix}-{uuid.uuid5(uuid.NAMESPACE_URL, source)}"


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


def has_traded(ticker, trade_file=None):
    return any(row["ticker"] == ticker for row in read_trade_rows(trade_file))


def contracts_for_budget(entry_price, budget=PAPER_TRADE_BUDGET):
    return size_contracts(entry_price, budget)


def record_paper_trade(
    ticker,
    side,
    prediction,
    entry_price,
    model_probability,
    edge,
    strategy_name="",
    seconds_remaining="",
    contracts=1,
    *,
    trade_file=None,
):
    trade_file = trade_file or TRADE_FILE

    entry_price = Decimal(str(entry_price))
    model_probability = Decimal(str(model_probability))
    edge = Decimal(str(edge))
    contracts = int(contracts)
    cost = entry_price * contracts

    with paper_ledger_lock(trade_file):
        _initialize_trade_file(trade_file)
        with open(trade_file, "r", newline="") as file:
            if any(row["ticker"] == ticker for row in csv.DictReader(file)):
                return False
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_id": f"paper-{uuid.uuid4()}",
            "ticker": ticker,
            "side": side,
            "prediction": prediction,
            "entry_price": f"{entry_price:.4f}",
            "model_probability": f"{model_probability:.4f}",
            "edge": f"{edge:.4f}",
            "strategy_name": strategy_name,
            "seconds_remaining": (
                f"{Decimal(str(seconds_remaining)):.4f}"
                if seconds_remaining not in (None, "")
                else ""
            ),
            "contracts": contracts,
            "cost": f"{cost:.4f}",
            "actual_result": "",
            "profit_loss": "",
            "correct": "",
        }
        with open(trade_file, "a", newline="") as file:
            csv.DictWriter(file, fieldnames=FIELDNAMES).writerow(row)

    return True


def update_paper_trade_results(
    get_market_result, *, trade_file=None, on_error=None, should_stop=None, on_progress=None,
):
    trade_file = trade_file or TRADE_FILE
    rows = read_trade_rows(trade_file)
    updated_count = 0

    for row in rows:
        if should_stop is not None and should_stop():
            break
        if row.get("actual_result"):
            continue

        ticker = row.get("ticker")
        if not ticker:
            continue

        settled = 0
        try:
            result = get_market_result(ticker)
            if result in ("YES", "NO"):
                update = {
                    "actual_result": result,
                    "profit_loss": calculate_profit_loss(row, result),
                    "correct": str(row.get("side") == result),
                }
                # Lookups run without the lock; only the saved row is merged.
                with paper_ledger_lock(trade_file):
                    with open(trade_file, "r", newline="") as file:
                        current_rows = list(csv.DictReader(file))
                    for current in current_rows:
                        if current.get("trade_id") == row["trade_id"] and not current.get("actual_result"):
                            current.update(update)
                            settled += 1
                    if settled:
                        _write_trade_rows(current_rows, trade_file)
                if settled:
                    print(f"Settled paper trade {ticker} | P/L: {update['profit_loss']}", flush=True)
        except Exception as exc:
            settled = 0
            message = f"Could not settle paper trade {ticker}: {exc}"
            print(message, flush=True)
            if on_error is not None:
                on_error(message)
        updated_count += settled
        if on_progress is not None:
            on_progress(settled)

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
