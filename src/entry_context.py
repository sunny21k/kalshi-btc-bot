"""Entry observations kept beside a trade ledger without changing its CSV schema."""

import json
from decimal import Decimal
from pathlib import Path


ENTRY_FIELDS = (
    "entry_direction", "entry_direction_basis", "entry_direction_match",
    "entry_observed_at", "entry_btc_price", "entry_btc_change_usd",
    "entry_btc_change_pct", "entry_window_prices", "match_offset_seconds",
)


def direction(value):
    value = Decimal(str(value))
    return "UNKNOWN" if not value.is_finite() else "UP" if value > 0 else "DOWN" if value < 0 else "FLAT"


def match_direction(side, observed):
    if observed not in ("UP", "DOWN", "FLAT") or side not in ("YES", "NO"):
        return "UNKNOWN"
    if observed == "FLAT":
        return "FLAT"
    return "MATCH" if observed == ("UP" if side == "YES" else "DOWN") else "OPPOSITE"


def make_entry_context(prices, *, side, bot_id, observed_at):
    prices = [Decimal(str(price)) for price in prices][-4:]
    change = prices[-1] - prices[-2] if len(prices) >= 2 else None
    observed = direction(change) if change is not None else "UNKNOWN"
    return {
        "bot_id": bot_id,
        "entry_direction": observed,
        "entry_direction_basis": "RECORDED",
        "entry_direction_match": match_direction(side, observed),
        "entry_observed_at": observed_at,
        "entry_btc_price": str(prices[-1]) if prices else "",
        "entry_btc_change_usd": str(change) if change is not None else "",
        "entry_btc_change_pct": str(change / prices[-2] * 100) if change is not None and prices[-2] else "",
        "entry_window_prices": json.dumps([str(price) for price in prices]),
    }


def append_entry_context(trade_file, row, context):
    # Called under the ledger lock, before committing the entry/order attempt.
    with open(f"{trade_file}.entries.jsonl", "a") as file:
        file.write(json.dumps({**context, **{key: row[key] for key in ("trade_id", "timestamp", "ticker", "side")}}, allow_nan=False) + "\n")


def read_entry_contexts(trade_file):
    path = Path(f"{trade_file}.entries.jsonl")
    if not path.exists():
        return {}
    contexts = {}
    with path.open() as file:
        for line in file:
            try:
                row = json.loads(line)
                if isinstance(row, dict) and row.get("trade_id"):
                    contexts[row["trade_id"]] = row
            except ValueError:
                continue  # A concurrent append or damaged observation stays unknown.
    return contexts


def attach_entry_directions(rows, trade_file, audit_rows=()):
    contexts = {row["trade_id"]: row for row in audit_rows if row.get("source_file") == Path(trade_file).name and row.get("trade_id")}
    contexts.update(read_entry_contexts(trade_file))
    return [
        {**row, **{key: context.get(key, "") for key in ENTRY_FIELDS}}
        if (context := contexts.get(row.get("trade_id"))) and context.get("ticker") == row.get("ticker") and context.get("side") == row.get("side")
        else row
        for row in rows
    ]
