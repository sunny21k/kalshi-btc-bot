import csv
import fcntl
import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from kalshi_api import create_order, get_order_fills


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
    "fill_cost",
    "fees_paid",
    "pnl_basis",
    "sync_error",
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


@contextmanager
def live_ledger_lock():
    Path(LIVE_TRADE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(f"{LIVE_TRADE_FILE}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def initialize_live_trade_file():
    with live_ledger_lock():
        _initialize_live_trade_file()


def _initialize_live_trade_file():
    if not os.path.exists(LIVE_TRADE_FILE) or os.path.getsize(LIVE_TRADE_FILE) == 0:
        _write_live_trade_rows([])
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
    backup = f"{LIVE_TRADE_FILE}.backup-{uuid.uuid4().hex[:8]}"
    shutil.copy2(LIVE_TRADE_FILE, backup)
    _write_live_trade_rows(migrated_rows)


def normalize_live_trade_row(row):
    normalized = {field: row.get(field) or "" for field in FIELDNAMES}
    if not normalized["trade_id"]:
        normalized["trade_id"] = legacy_trade_id("live", normalized)
    if normalized["side"] not in ("YES", "NO") or not normalized["ticker"]:
        normalized["error"] = normalized["error"] or "Malformed legacy row; see CSV backup"
    normalized["fill_status"] = live_fill_status(normalized)
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
    with live_ledger_lock():
        _write_live_trade_rows(rows)


def _write_live_trade_rows(rows):
    directory = Path(LIVE_TRADE_FILE).parent
    fd, temporary_path = tempfile.mkstemp(dir=directory, prefix=".live-trades-")
    try:
        with os.fdopen(fd, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, LIVE_TRADE_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def read_live_trade_rows():
    with live_ledger_lock():
        _initialize_live_trade_file()
        with open(LIVE_TRADE_FILE, "r", newline="") as file:
            return list(csv.DictReader(file))


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
        "fill_count_fp",
        "filled_count_fp",
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

    return ""


def live_filled_count(row):
    value = row.get("filled_count")
    if value in (None, "") and row.get("status", "").lower() in ("executed", "filled"):
        value = row.get("submitted_count") or row.get("contracts")
    if value in (None, ""):
        return None
    try:
        count = Decimal(str(value))
    except InvalidOperation:
        return None
    return count if count.is_finite() and count >= 0 else None


def live_fill_status(row):
    if row.get("error"):
        return "REJECTED"
    count = live_filled_count(row)
    if count is None:
        return "UNKNOWN"
    if not count:
        return "UNFILLED"
    submitted = Decimal(str(row.get("submitted_count") or row.get("contracts") or count))
    return "FILLED" if count >= submitted else "PARTIAL"


def append_live_trade_row(row):
    with live_ledger_lock():
        _initialize_live_trade_file()
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
        "fill_cost": "",
        "fees_paid": "",
        "pnl_basis": "",
        "sync_error": "",
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
    completed_row["fill_status"] = live_fill_status(completed_row)
    completed_row["response"] = json.dumps(response, sort_keys=True)
    append_live_trade_row(completed_row)

    return True


def apply_order_fills(row, fills):
    count = Decimal("0")
    cost = Decimal("0")
    fees = Decimal("0")
    complete_fees = True
    for fill in fills:
        if fill.get("order_id") != row["order_id"]:
            raise ValueError("Fill does not match logged order")
        ticker = fill.get("ticker") or fill.get("market_ticker")
        if ticker != row["ticker"]:
            raise ValueError("Fill does not match logged market")
        quantity = Decimal(str(fill.get("count_fp", fill.get("count", ""))))
        price_key = row["side"].lower()
        price = fill.get(f"{price_key}_price_dollars")
        if price in (None, ""):
            price = Decimal(str(fill[f"{price_key}_price"])) / Decimal("100")
        price = Decimal(str(price))
        if not quantity.is_finite() or quantity <= 0 or not price.is_finite() or not 0 <= price <= 1:
            raise ValueError("Invalid fill quantity or price")
        count += quantity
        cost += quantity * price
        fee = fill.get("fee_cost")
        if fee in (None, ""):
            complete_fees = False
        else:
            fee = Decimal(str(fee))
            if not fee.is_finite():
                raise ValueError("Invalid fill fee")
            fees += fee

    row["filled_count"] = str(count)
    row["fill_cost"] = f"{cost:.4f}"
    row["fees_paid"] = f"{fees:.4f}" if complete_fees else ""
    row["fill_status"] = live_fill_status(row)
    row["sync_error"] = "" if complete_fees else "Fill fees unavailable; net P/L pending"


def update_live_trade_results(get_market_result, *, get_fills_fn=get_order_fills):
    rows = read_live_trade_rows()
    updates = {}
    results = {}
    updated_count = 0

    for row in rows:
        if row.get("error"):
            continue
        if row.get("pnl_basis") == "ACTUAL" and row.get("profit_loss") not in (None, ""):
            continue
        if not row.get("order_id") or row.get("side") not in ("YES", "NO"):
            continue

        original = dict(row)
        try:
            fills = get_fills_fn(row["order_id"], ticker=row["ticker"])
            if not fills and (live_filled_count(row) or Decimal("0")) > 0:
                raise ValueError("Recorded fill not found in exchange history; P/L unverified")
            apply_order_fills(row, fills)
            row["profit_loss"] = ""
            row["correct"] = ""
            row["pnl_basis"] = ""
            row["actual_result"] = ""
            if not fills:
                row["profit_loss"] = "0.0000"
                row["pnl_basis"] = "NO_FILL"
            else:
                ticker = row["ticker"]
                if ticker not in results:
                    results[ticker] = get_market_result(ticker)
                result = results[ticker]
                if result in ("YES", "NO") and row["fees_paid"] != "":
                    row["actual_result"] = result
                    row["profit_loss"] = calculate_profit_loss(row, result)
                    row["correct"] = str(row["side"] == result)
                    row["pnl_basis"] = "ACTUAL"
                    updated_count += 1
        except Exception as exc:
            # A failed lookup must not turn an unknown fill into a fabricated P/L.
            row = original.copy()
            row["sync_error"] = str(exc)
            print(f"Could not reconcile live order {row['order_id']}: {exc}", flush=True)

        if row != original:
            updates[row["trade_id"]] = row

    if updates:
        # Merge after network requests so newly appended orders are preserved.
        with live_ledger_lock():
            with open(LIVE_TRADE_FILE, "r", newline="") as file:
                current_rows = list(csv.DictReader(file))
            _write_live_trade_rows([
                updates.get(row.get("trade_id"), row) for row in current_rows
            ])

    return updated_count


def calculate_profit_loss(row, actual_result):
    count = live_filled_count(row)
    if count is None or row.get("fill_cost") in (None, "") or row.get("fees_paid") in (None, ""):
        return ""
    payout = count if row["side"] == actual_result else Decimal("0")
    profit_loss = payout - Decimal(row["fill_cost"]) - Decimal(row["fees_paid"])
    return f"{profit_loss:.4f}"


if __name__ == "__main__":
    from outcome_tracker import get_market_result

    print("Reconciling live fills and settled P/L...")
    count = update_live_trade_results(get_market_result)
    print(f"Live trades settled: {count}")
