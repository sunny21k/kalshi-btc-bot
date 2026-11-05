"""Read-only history audit; old entry directions are inferred, never backfilled as facts."""

import argparse
import csv
import os
import tempfile
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from entry_context import ENTRY_FIELDS, direction, match_direction, read_entry_contexts


REPORT_FILE = "data/trade_direction_audit.csv"
DEFAULT_TRADES = ("data/paper_trades.csv", "data/dual_paper_trades.csv", "data/direction_paper_trades.csv", "data/live_trades.csv")
DEFAULT_MARKETS = ("data/market_data.csv", "data/direction_market_data.csv")
REPORT_FIELDS = ("source_file", "trade_id", "timestamp", "ticker", "side", "entry_price", "strategy_name", "actual_result", "profit_loss", *ENTRY_FIELDS)


def number(value):
    try:
        value = Decimal(str(value))
        return value if value.is_finite() else None
    except InvalidOperation:
        return None


def timestamp(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.timestamp() if date.tzinfo is not None else None
    except (ValueError, AttributeError, OverflowError):
        return None


def read_rows(path):
    if not Path(path).exists():
        return []
    with open(path, newline="") as file:
        return list(csv.DictReader(file))


def compatible_quote(trade, sample):
    price = number(trade.get("entry_price"))
    quote = number(sample.get("yes_ask" if trade["side"] == "YES" else "yes_bid"))
    if price is None or quote is None:
        return False
    if price > 1:
        price /= 100
    if quote > 1:
        quote /= 100
    if trade["side"] == "NO":
        quote = 1 - quote
    if not 0 <= quote <= 1 or abs(price - quote) > Decimal("0.0001"):
        return False
    remaining = number(trade.get("seconds_remaining"))
    observed = number(sample.get("seconds_remaining"))
    return remaining is None or (observed is not None and abs(remaining - observed) <= Decimal("0.001"))


def audit_trades(trade_files, market_files, *, max_age_seconds=2):
    trades = []
    candidates = defaultdict(list)
    pending = defaultdict(list)
    for path in trade_files:
        snapshots = read_entry_contexts(path)
        for row in read_rows(path):
            if row.get("side") not in ("YES", "NO") or row.get("error"):
                continue
            if "filled_count" in row and (number(row.get("filled_count")) or 0) <= 0:
                continue
            item = {key: row.get(key, "") for key in REPORT_FIELDS}
            item.update(source_file=Path(path).name, entry_direction="UNKNOWN", entry_direction_basis="UNKNOWN", entry_direction_match="UNKNOWN")
            index = len(trades)
            trades.append(item)
            snapshot = snapshots.get(row.get("trade_id"))
            if snapshot and snapshot.get("ticker") == row["ticker"] and snapshot.get("side") == row["side"]:
                item.update({key: snapshot.get(key, "") for key in ENTRY_FIELDS})
                continue
            entry_time = timestamp(row.get("timestamp"))
            if entry_time is not None:
                pending[row["ticker"]].append((entry_time, index, row))
    pending = {ticker: sorted(rows, key=lambda row: (row[0], row[1])) for ticker, rows in pending.items()}
    times = {ticker: [row[0] for row in rows] for ticker, rows in pending.items()}
    for path in market_files:
        if not Path(path).exists():
            continue
        with open(path, newline="") as file:
            for sample in csv.DictReader(file):
                ticker = sample.get("ticker")
                if ticker not in pending:
                    continue
                observed_at = timestamp(sample.get("timestamp"))
                change = number(sample.get("btc_change"))
                price = number(sample.get("btc_price"))
                if observed_at is None or change is None or price is None or price <= 0:
                    continue
                for entry_at, index, trade in pending[ticker][bisect_left(times[ticker], observed_at):bisect_right(times[ticker], observed_at + max_age_seconds)]:
                    if compatible_quote(trade, sample):
                        candidates[index].append((entry_at - observed_at, sample, direction(change)))
    for index, matches in candidates.items():
        item = trades[index]
        if len({observed for _, _, observed in matches}) > 1:
            item["entry_direction_basis"] = "AMBIGUOUS"
            continue
        age, sample, observed = min(matches, key=lambda match: match[0])
        item.update(
            entry_direction=observed, entry_direction_basis="INFERRED",
            entry_direction_match=match_direction(item["side"], observed),
            entry_observed_at=sample["timestamp"], entry_btc_price=sample["btc_price"],
            entry_btc_change_pct=sample["btc_change"], match_offset_seconds=f"{age:.4f}",
        )
    return trades


def write_report(rows, output):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".direction-audit-")
    try:
        with os.fdopen(descriptor, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", action="append", help="Trade CSV to inspect; repeat for multiple ledgers")
    parser.add_argument("--market-data", action="append", help="Market observations CSV; repeat if needed")
    parser.add_argument("--output", default=REPORT_FILE)
    args = parser.parse_args()
    trade_files = args.trades or DEFAULT_TRADES
    market_files = args.market_data or DEFAULT_MARKETS
    protected = {Path(path).resolve() for path in (*DEFAULT_TRADES, *DEFAULT_MARKETS, *trade_files, *market_files)}
    protected.update(Path(f"{path}.entries.jsonl").resolve() for path in (*DEFAULT_TRADES, *trade_files))
    if Path(args.output).resolve() in protected:
        parser.error("The report must not overwrite an input file")
    rows = audit_trades(trade_files, market_files)
    write_report(rows, args.output)
    for basis in ("RECORDED", "INFERRED", "AMBIGUOUS", "UNKNOWN"):
        print(f"{basis}: {sum(row['entry_direction_basis'] == basis for row in rows)}")
    print(f"Report: {args.output}")
    print("Inferred directions use matching observations at most 2 seconds before the entry; interleaved bot logs cannot prove the exact source.")


if __name__ == "__main__":
    main()
