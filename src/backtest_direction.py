"""Offline, approximate replay of the original and direction-filtered paper rules."""

import argparse
import csv
import hashlib
import heapq
import json
import math
import os
import tempfile
from collections import Counter, defaultdict, deque
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import count
from pathlib import Path

from direction_strategy import make_direction_paper_decision
from strategy import make_dual_live_decision, make_late_momentum_decision
from trade_sizing import contracts_for_budget, parse_trade_budget


DEFAULT_MARKETS = ("data/market_data.csv", "data/direction_market_data.csv")
DEFAULT_RESULTS = ("data/prediction_results.csv", "data/paper_trades.csv", "data/dual_paper_trades.csv", "data/direction_paper_trades.csv", "data/live_trades.csv")
TRADE_FIELDS = (
    "variant", "timestamp", "ticker", "side", "strategy_name", "entry_price",
    "contracts", "cost", "btc_price", "target_price", "price_difference",
    "seconds_remaining", "recent_prices", "actual_result", "gross_profit_loss",
    "assumed_cost", "net_profit_loss", "profit_loss_after_1c_per_contract",
)


def number(value):
    try:
        value = Decimal(str(value))
        return value if value.is_finite() else None
    except InvalidOperation:
        return None


def instant(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.timestamp() if date.tzinfo else None
    except (AttributeError, ValueError, OverflowError):
        return None


def money(value):
    return f"{value:.4f}"


def rows(path):
    if Path(path).exists():
        with open(path, newline="") as file:
            yield from csv.DictReader(file)


def freeze_input(source, destination):
    """Copy only bytes present when the source is opened; omit a partial last row."""
    digest = hashlib.sha256()
    with open(source, 'rb') as incoming, open(destination, 'w+b') as frozen:
        stats = os.fstat(incoming.fileno())
        remaining = stats.st_size
        while remaining:
            chunk = incoming.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            frozen.write(chunk)
            remaining -= len(chunk)
        end = frozen.tell()
        if end:
            frozen.seek(end - 1)
            if frozen.read(1) != b'\n':
                cursor = end
                while cursor:
                    start = max(0, cursor - 65536)
                    frozen.seek(start)
                    tail = frozen.read(cursor - start)
                    newline = tail.rfind(b'\n')
                    if newline >= 0:
                        frozen.truncate(start + newline + 1)
                        break
                    cursor = start
                else:
                    frozen.truncate(0)
        frozen.seek(0)
        while chunk := frozen.read(1024 * 1024):
            digest.update(chunk)
        snapshot_bytes = frozen.tell()
    return stats, dict(snapshot_bytes=snapshot_bytes, snapshot_sha256=digest.hexdigest())


def chronological(path, quality, *, reorder_seconds=2):
    """Sort small concurrent-write inversions; discard any larger late arrivals."""
    buffer = []
    sequence = count()
    newest = float('-inf')
    emitted = float('-inf')
    for row in rows(path):
        quality['rows_read'] += 1
        stamp = instant(row.get('timestamp'))
        if stamp is None:
            quality['invalid_timestamps'] += 1
            continue
        if stamp < emitted:
            quality['late_rows_discarded'] += 1
            continue
        newest = max(newest, stamp)
        heapq.heappush(buffer, (stamp, next(sequence), row))
        while buffer and buffer[0][0] <= newest - reorder_seconds:
            stamp, _, row = heapq.heappop(buffer)
            emitted = stamp
            yield stamp, row
    while buffer:
        stamp, _, row = heapq.heappop(buffer)
        yield stamp, row


class TargetResolver:
    def __init__(self, observations, quality):
        self.observations = iter(observations)
        self.next = next(self.observations, None)
        self.cache = defaultdict(list)
        self.expiry = deque()
        self.known = {}
        self.conflicts = set()
        self.quality = quality

    def resolve(self, stamp, ticker, seconds, btc):
        while self.next and self.next[0] <= stamp:
            observed_at, row = self.next
            remaining = number(row.get('seconds_remaining'))
            difference = number(row.get('price_difference'))
            if remaining is not None and difference is not None:
                key = (row.get('ticker'), remaining)
                item = (observed_at, difference)
                self.cache[key].append(item)
                self.expiry.append((observed_at, key, item))
            self.next = next(self.observations, None)
        while self.expiry and self.expiry[0][0] < stamp - 2:
            _, key, item = self.expiry.popleft()
            self.cache[key].remove(item)
            if not self.cache[key]:
                del self.cache[key]
        matches = {btc - difference for _, difference in self.cache.get((ticker, seconds), [])}
        if len(matches) > 1:
            self.quality['ambiguous_target_observations'] += 1
            return None
        if matches:
            target = next(iter(matches))
            self.quality['joined_target_observations'] += 1
            if target <= 0 or (ticker in self.known and abs(target - self.known[ticker]) > Decimal('0.01')):
                self.conflicts.add(ticker)
                return None
            self.known[ticker] = target
        return None if ticker in self.conflicts else self.known.get(ticker)


def recorded_outcomes(paths):
    observations = defaultdict(set)
    for path in paths:
        for row in rows(path):
            ticker = row.get('ticker')
            result = (row.get('actual_result') or '').strip().upper()
            if ticker and result in ('YES', 'NO'):
                observations[ticker].add(result)
    return ({ticker: next(iter(results)) for ticker, results in observations.items() if len(results) == 1},
            {ticker for ticker, results in observations.items() if len(results) > 1})


def observations(market_paths, shadow_path, quality):
    shadow_quality = Counter()
    resolver = TargetResolver(chronological(shadow_path, shadow_quality), quality)
    streams = [chronological(path, quality) for path in market_paths if Path(path).exists()]
    merged = heapq.merge(*streams, key=lambda item: item[0])
    for stamp, row in merged:
        ticker = row.get('ticker')
        btc = number(row.get('btc_price'))
        seconds = number(row.get('seconds_remaining'))
        bid = number(row.get('yes_bid'))
        ask = number(row.get('yes_ask'))
        spread = number(row.get('spread'))
        if not ticker or any(value is None for value in (btc, seconds, bid, ask, spread)) or btc <= 0:
            quality['invalid_market_observations'] += 1
            continue
        if ask > 1 or bid > 1:
            bid, ask = bid / 100, ask / 100
            spread /= 100
        if not 0 <= bid <= ask <= 1 or spread < 0 or abs(ask - bid - spread) > Decimal('0.0001'):
            quality['invalid_quotes'] += 1
            continue
        target = resolver.resolve(stamp, ticker, seconds, btc)
        yield dict(stamp=stamp, timestamp=row['timestamp'], ticker=ticker, btc_price=btc,
                   target_price=target, seconds_remaining=seconds, yes_ask=ask, no_ask=1 - bid, spread=spread)
    quality['target_markets'] = len(resolver.known)
    quality['conflicting_target_markets'] = len(resolver.conflicts)
    quality['shadow_rows_read'] = shadow_quality['rows_read']
    quality['shadow_invalid_timestamps'] = shadow_quality['invalid_timestamps']
    quality['shadow_late_rows_discarded'] = shadow_quality['late_rows_discarded']
    return resolver.conflicts


def comparison_variants(comparison):
    if comparison == 'direction':
        return {'original': make_late_momentum_decision, 'direction': make_direction_paper_decision}
    if comparison == 'strong-min-80':
        return {'original': make_late_momentum_decision, 'live_80c': make_dual_live_decision}
    raise ValueError('Unknown backtest comparison')


def replay(tape, outcomes, *, budget='100', sample_seconds=5, max_gap_seconds=30, cost_per_contract='0', quality=None, comparison='direction'):
    budget = parse_trade_budget(budget)
    friction = number(cost_per_contract)
    if friction is None or friction < 0:
        raise ValueError('Assumed cost per contract must be finite and nonnegative')
    if not all(math.isfinite(value) for value in (sample_seconds, max_gap_seconds)) or sample_seconds <= 0 or max_gap_seconds < sample_seconds:
        raise ValueError('Sampling interval must be positive and no longer than the maximum gap')
    quality = quality if quality is not None else Counter()
    recent = deque(maxlen=4)
    confirmations = {}
    variants = comparison_variants(comparison)
    asks = {name: {} for name in variants}
    entered = {name: set() for name in variants}
    trades = []
    last_sample = None
    for sample in tape:
        stamp = sample['stamp']
        if last_sample is not None and stamp < last_sample + sample_seconds:
            quality['subinterval_rows_skipped'] += 1
            continue
        if last_sample is not None and stamp - last_sample > max_gap_seconds:
            recent.clear()
            confirmations.clear()
            for previous in asks.values():
                previous.clear()
            quality['gap_resets'] += 1
        last_sample = stamp
        quality['sampled_observations'] += 1
        recent.append(sample['btc_price'])
        target = sample['target_price']
        if target is None:
            quality['sampled_without_target'] += 1
            continue
        quality['sampled_with_target'] += 1
        ticker = sample['ticker']
        difference = sample['btc_price'] - target
        key = None
        if abs(difference) >= 10:
            key = (ticker, 'YES' if difference > 0 else 'NO')
            confirmations[key] = confirmations.get(key, 0) + 1
        else:
            confirmations[(ticker, 'YES')] = confirmations[(ticker, 'NO')] = 0
        for variant, decide in variants.items():
            signal = decide(
                btc_price=sample['btc_price'], target_price=target,
                seconds_remaining=sample['seconds_remaining'], yes_ask=sample['yes_ask'],
                no_ask=sample['no_ask'], spread=sample['spread'], recent_prices=recent,
                previous_entry_price=asks[variant].get(key), confirmation_count=confirmations.get(key, 0),
                enable_early_up=False,
            )
            if signal.get('side'):
                asks[variant][(ticker, signal['side'])] = signal.get('entry_price')
            if not signal['decision'].startswith('BUY ') or ticker in entered[variant]:
                continue
            price = signal['entry_price']
            try:
                contracts = contracts_for_budget(price, budget)
            except ValueError:
                quality['unaffordable_entries'] += 1
                continue
            entered[variant].add(ticker)
            # Outcomes are accessed only after the decision and entry are fixed.
            result = outcomes.get(ticker, '')
            cost = price * contracts
            gross = (Decimal(int(signal['side'] == result)) - price) * contracts if result in ('YES', 'NO') else None
            assumed_cost = friction * contracts if gross is not None else None
            trades.append(dict(
                variant=variant, timestamp=sample['timestamp'], ticker=ticker, side=signal['side'],
                strategy_name=signal['strategy_name'], entry_price=str(price), contracts=contracts,
                cost=money(cost), btc_price=str(sample['btc_price']), target_price=str(target),
                price_difference=str(difference), seconds_remaining=str(sample['seconds_remaining']),
                recent_prices=json.dumps([str(value) for value in recent]), actual_result=result,
                gross_profit_loss=money(gross) if gross is not None else '',
                assumed_cost=money(assumed_cost) if assumed_cost is not None else '',
                net_profit_loss=money(gross - assumed_cost) if gross is not None else '',
                profit_loss_after_1c_per_contract=money(gross - Decimal('0.01') * contracts) if gross is not None else '',
            ))
    return trades


def summarize(trades):
    settled = [row for row in trades if row['actual_result'] in ('YES', 'NO')]
    cost = sum((Decimal(row['cost']) for row in settled), Decimal(0))
    gross = sum((Decimal(row['gross_profit_loss']) for row in settled), Decimal(0))
    net = sum((Decimal(row['net_profit_loss']) for row in settled), Decimal(0))
    wins = sum(row['side'] == row['actual_result'] for row in settled)
    return dict(entries=len(trades), settled=len(settled), pending=len(trades)-len(settled), wins=wins,
                win_rate_pct=round(wins / len(settled) * 100, 2) if settled else None,
                settled_entry_cost=money(cost), total_entry_cost=money(sum((Decimal(row['cost']) for row in trades), Decimal(0))),
                gross_profit_loss=money(gross), net_profit_loss=money(net),
                gross_roi_pct=round(float(gross / cost * 100), 2) if cost else None,
                profit_loss_after_1c_per_contract=money(sum((Decimal(row['profit_loss_after_1c_per_contract']) for row in settled), Decimal(0))))


def report(trades, quality, metadata):
    comparison = {}
    for variant in comparison_variants(metadata.get('comparison_name', 'direction')):
        selected = [row for row in trades if row['variant'] == variant]
        comparison[variant] = {
            **summarize(selected),
            'by_strategy': {name: summarize([row for row in selected if row['strategy_name'] == name]) for name in sorted({row['strategy_name'] for row in selected})},
            'by_side': {side: summarize([row for row in selected if row['side'] == side]) for side in ('YES', 'NO')},
        }
    return {**metadata, 'quality': dict(quality), 'comparison': comparison}


def write_reports(trades, summary, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'trades.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=TRADE_FIELDS)
        writer.writeheader()
        writer.writerows(trades)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    dollars = lambda value: f"{'-' if Decimal(value) < 0 else ''}${abs(Decimal(value)):,.2f}"
    lines = ['# Approximate paper-rule backtest', '', 'Paper simulation using reconstructed observations, not verified historical fills.', '',
             f"Entry budget: ${summary['budget']} before fees. Eligible simulated entries: {summary['trade_start']} through {summary['trade_end']}.", '',
             '| Variant | Settled trades | Win rate | Gross P/L | Gross ROI | P/L with $0.01/contract cost |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for variant, stats in summary['comparison'].items():
        lines.append(f"| {variant} | {stats['settled']} | {stats['win_rate_pct']}% | {dollars(stats['gross_profit_loss'])} | {stats['gross_roi_pct']}% | {dollars(stats['profit_loss_after_1c_per_contract'])} |")
    lines.extend(['', '## By entry rule', '', '| Variant | Rule | Settled trades | Win rate | Gross P/L |', '| --- | --- | ---: | ---: | ---: |'])
    for variant, stats in summary['comparison'].items():
        for rule, values in stats['by_strategy'].items():
            lines.append(f"| {variant} | {rule} | {values['settled']} | {values['win_rate_pct']}% | {dollars(values['gross_profit_loss'])} |")
    lines.extend(['', '## By purchased side', '', '| Variant | Side | Settled trades | Win rate | Gross P/L |', '| --- | --- | ---: | ---: | ---: |'])
    for variant, stats in summary['comparison'].items():
        for side, values in stats['by_side'].items():
            lines.append(f"| {variant} | {side} | {values['settled']} | {values['win_rate_pct']}% | {dollars(values['gross_profit_loss'])} |")
    lines.extend(['', '## Assumptions and limits', '', *['- ' + note for note in summary['limitations']], '',
                  '## Data quality', '', '```json', json.dumps(summary['quality'], indent=2), '```', ''])
    (output / 'report.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--market-data', action='append')
    parser.add_argument('--shadow-data', default='data/shadow_signals.csv')
    parser.add_argument('--results', action='append')
    parser.add_argument('--budget', default='100')
    parser.add_argument('--sample-seconds', type=float, default=5)
    parser.add_argument('--max-gap-seconds', type=float, default=30)
    parser.add_argument('--cost-per-contract', default='0')
    parser.add_argument('--compare', choices=('direction', 'strong-min-80'), default='direction')
    parser.add_argument('--output-dir')
    args = parser.parse_args()
    output_dir = args.output_dir or ('data/backtests/live_80c' if args.compare == 'strong-min-80' else 'data/backtests/direction')
    market_paths = args.market_data or DEFAULT_MARKETS
    result_paths = args.results or DEFAULT_RESULTS
    all_inputs = (*market_paths, args.shadow_data, *result_paths)
    outputs = [Path(output_dir) / name for name in ('trades.csv', 'summary.json', 'report.md')]
    if {path.resolve() for path in outputs} & {Path(path).resolve() for path in all_inputs}:
        parser.error('Reports cannot overwrite input files')
    if not any(Path(path).exists() for path in market_paths) or not Path(args.shadow_data).exists():
        parser.error('Both market observations and shadow observations are required')
    with tempfile.TemporaryDirectory(prefix='kalshi-backtest-') as temporary:
        frozen_paths, input_stats, snapshots = {}, {}, {}
        for index, path in enumerate(dict.fromkeys(all_inputs)):
            frozen = Path(temporary) / f'{index}.csv'
            frozen_paths[path] = str(frozen)
            if Path(path).exists():
                stats, metadata = freeze_input(path, frozen)
                input_stats[str(path)] = stats
                snapshots[str(path)] = metadata
        run_backtest(args, [frozen_paths[path] for path in market_paths], frozen_paths[args.shadow_data],
                     [frozen_paths[path] for path in result_paths], output_dir, input_stats, snapshots)


def run_backtest(args, market_paths, shadow_path, result_paths, output_dir, input_stats, snapshots):
    outcomes, conflicting_outcomes = recorded_outcomes(result_paths)
    quality = Counter()
    quality['conflicting_outcome_markets'] = len(conflicting_outcomes)
    # Capture target conflicts when the tape generator finishes, without retaining the full log.
    tape = observations(market_paths, shadow_path, quality)
    conflicts = set()
    first = last = None
    def tracked():
        nonlocal first, last, conflicts
        while True:
            try:
                sample = next(tape)
            except StopIteration as completed:
                conflicts = completed.value or set()
                return
            first = first or sample['timestamp']
            last = sample['timestamp']
            yield sample
    trades = replay(tracked(), outcomes, budget=args.budget, sample_seconds=args.sample_seconds,
                    max_gap_seconds=args.max_gap_seconds, cost_per_contract=args.cost_per_contract, quality=quality, comparison=args.compare)
    quality['entries_excluded_for_target_conflicts'] = sum(row['ticker'] in conflicts for row in trades)
    trades = [row for row in trades if row['ticker'] not in conflicts]
    source = Path(__file__).parent
    strategy_hash = hashlib.sha256(b''.join((source / name).read_bytes() for name in ('strategy.py', 'direction_strategy.py', 'backtest_direction.py'))).hexdigest()
    metadata = dict(
        approximation=True, frozen_inputs=True, comparison_name=args.compare, observation_start=first, observation_end=last,
        trade_start=min((row['timestamp'] for row in trades), default=None),
        trade_end=max((row['timestamp'] for row in trades), default=None),
        budget=str(parse_trade_budget(args.budget)), sample_seconds=args.sample_seconds,
        max_gap_seconds=args.max_gap_seconds, assumed_cost_per_contract=args.cost_per_contract,
        strategy_hash=strategy_hash,
        inputs=[{'path': path, 'bytes': stats.st_size, **snapshots[path], 'source_changed_during_run': (Path(path).stat().st_size, Path(path).stat().st_mtime_ns) != (stats.st_size, stats.st_mtime_ns)} for path, stats in input_stats.items()],
        limitations=[
            'Inputs are frozen to temporary copies before replay. New rows appended by running bots are excluded from those snapshots; the source paths, snapshot sizes, and hashes are recorded.',
            'Historical bot IDs and full per-bot price windows were not logged. The shared observations are reconstructed into one stream, taking the first observation at least one sampling interval after the previous sample.',
            'Targets are inferred only from matching shadow observations at or before the market observation; known targets are then carried forward. No future observations are used to choose entries.',
            'Both variants use the same reconstructed tape and budget. Gaps longer than the configured maximum reset price history, confirmations, and chase checks.',
            'The original comparator uses the current YES/NO rules, not each old strategy version or its original contract quantities.',
            'Settlement uses recorded market outcomes after entry decisions. Missing or conflicting outcomes stay pending, and target conflicts are excluded from both variants.',
            'Paper purchases assume all requested whole contracts fill at the recorded ask. Available depth, latency, actual fees, and slippage cannot be verified.',
            'Gross results exclude trading costs. The extra one-cent-per-contract column is a hypothetical cost scenario, not an exchange fee estimate.',
            'This is previously observed data used to design the strategy, not an independent forward test or proof of future profitability.',
        ],
    )
    summary = report(trades, quality, metadata)
    write_reports(trades, summary, output_dir)
    print(json.dumps(summary['comparison'], indent=2))
    print(f"Approximate replay reports: {output_dir}")
    print('Gross P/L excludes fees and assumes fills at recorded asks. See report.md for data limitations.')


if __name__ == '__main__':
    main()
