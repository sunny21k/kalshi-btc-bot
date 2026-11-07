"""Read-only trade-window replay from recorded observations and legacy logs."""

import csv
import json
import math
import re
import statistics
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from entry_rules import BOT_IDS
from replay_index import ReplayIndex, instant

WINDOW_SECONDS = 120
LEDGERS = dict(btc15_paper='paper_trades.csv', btc15_dual_paper='dual_paper_trades.csv',
    btc15_direction_paper='direction_paper_trades.csv', btc15_live='live_trades.csv',
    btc15_dual_live='live_trades.csv', scalp_paper='scalp_paper_trades.csv')


def number(value):
    try:
        value = Decimal(str(value))
        return value if value.is_finite() else None
    except (ValueError, InvalidOperation):
        return None


def scalar(value):
    value = number(value)
    return float(value) if value is not None and math.isfinite(float(value)) else None


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def locate_trade(root, bot_id, trade_id):
    if bot_id not in LEDGERS:
        raise ValueError('Unknown replay bot')
    path = Path(root) / 'data' / LEDGERS[bot_id]
    if not path.exists():
        raise LookupError('Trade history is unavailable')
    matches = []
    with path.open(newline='') as file:
        for row in csv.DictReader(file):
            if row.get('trade_id') != trade_id or row.get('side') not in ('YES', 'NO'):
                continue
            if bot_id in ('btc15_live', 'btc15_dual_live') and (row.get('bot_id') or 'btc15_live') != bot_id:
                continue
            matches.append(row)
    if not matches:
        raise LookupError('Trade not found in this bot’s history')
    if bot_id == 'scalp_paper':
        row = next((row for row in matches if row.get('event') == 'OPEN'), matches[0])
        anchor = row.get('opened_at') or (row.get('timestamp') if row.get('event') == 'OPEN' else None)
    else:
        row, anchor = matches[0], matches[0].get('timestamp')
    at = instant(anchor)
    if at is None:
        raise ValueError('The original entry timestamp is unavailable')
    live = bot_id in ('btc15_live', 'btc15_dual_live')
    filled = number(row.get('filled_count'))
    return dict(tradeId=trade_id, botId=bot_id, ticker=row['ticker'], side=row['side'], at=at,
        timestamp=iso(at), entryPrice=scalar(row.get('entry_price')), filled=bool(filled and filled > 0) if live else True,
        anchorLabel='Order attempt' if live else 'Paper entry', strategy=row.get('strategy_name') or row.get('reason') or '',
        secondsRemainingAtEntry=scalar(row.get('seconds_remaining')), marketCloseTime=row.get('close_time') or row.get('market_close_at'))


def market_period(entry):
    """Resolve the actual 15-minute period, never a window centered on a buy."""
    at = entry['at']
    close = instant(entry.get('marketCloseTime'))
    if close is not None and close - 900 <= at <= close + 30:
        return close - 900, close, 'recorded market close'
    match = re.fullmatch(r'KXBTC15M-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})-(\d{2})', entry['ticker'])
    months = {name: index + 1 for index, name in enumerate(('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'))}
    if match and match[2] in months and match[5] == match[6] and int(match[5]) in (0, 15, 30, 45):
        try:
            local = datetime(2000 + int(match[1]), months[match[2]], int(match[3]), int(match[4]), int(match[5]))
            zone = ZoneInfo('America/New_York')
            candidates = set()
            for fold in (0, 1):
                candidate = local.replace(tzinfo=zone, fold=fold).timestamp()
                if datetime.fromtimestamp(candidate, zone).replace(tzinfo=None) == local and candidate - 900 <= at <= candidate + 30:
                    candidates.add(candidate)
            if len(candidates) == 1:
                close = candidates.pop()
                return close - 900, close, 'market ticker in New York time'
        except (ValueError, OverflowError):
            pass
    remaining = number(entry.get('secondsRemainingAtEntry'))
    if remaining is not None and 0 <= remaining <= 900:
        estimated = at + float(remaining)
        close = round(estimated / 900) * 900
        if abs(estimated - close) <= 10 and close - 900 <= at <= close + 30:
            return close - 900, close, 'recorded countdown rounded to the market boundary'
    raise ValueError('The market period could not be determined from this trade. Choose the ±2-minute entry window instead.')


def observation_sources(root, at, *, start=None, end=None):
    root = Path(root)
    sources = [(root / 'data' / name, kind) for name, kind in (
        ('market_data.csv', 'market'), ('direction_market_data.csv', 'market'), ('shadow_signals.csv', 'shadow'))]
    start, end = (at - 120 if start is None else start), (at + 120 if end is None else end)
    dates = {datetime.fromtimestamp(value, timezone.utc).date().isoformat() for value in (start, end)}
    sources.extend((root / 'data' / 'replay' / bot_id / f'{date}.jsonl', 'recorded') for bot_id in BOT_IDS for date in sorted(dates))
    return [(path, kind) for path, kind in sources if path.exists()]


def normalize_window(records, entry, *, start=None, end=None):
    own = [(source, kind, at, row) for source, kind, at, row in records if kind == 'recorded' and row.get('bot_id') == entry['botId']]
    notes = ['Candles are reconstructed from sampled BTC prices, not full exchange candles. Exact live fill timestamps were not recorded; the marker uses the logged order-attempt time.' if entry['anchorLabel'] == 'Order attempt' else 'Candles are reconstructed from sampled BTC prices, not full exchange candles.']
    basis = 'recorded' if own else 'shared'
    chosen = own or [record for record in records if record[1] == 'market']
    if not chosen:
        chosen = [record for record in records if record[1] == 'recorded']
    shadows = defaultdict(list)
    live = entry['botId'] in ('btc15_live', 'btc15_dual_live')
    for _, kind, at, row in records:
        if kind == 'shadow' and row.get('ticker') == entry['ticker'] and row.get('live_enabled') in ('True', 'False') and (row.get('live_enabled') == 'True') == live:
            seconds = number(row.get('seconds_remaining'))
            difference = number(row.get('price_difference'))
            if seconds is not None:
                shadows[seconds].append((at, difference, row))
    points, targets, seen = [], set(), set()
    for source, kind, at, row in chosen:
        btc = number(row.get('btc_price'))
        btc_value = scalar(btc)
        if btc is None or btc <= 0 or btc_value is None:
            continue
        ticker = row.get('ticker')
        same_market = ticker == entry['ticker']
        bid, ask = number(row.get('yes_bid')), number(row.get('yes_ask'))
        scale = Decimal('100') if kind == 'market' and any(value is not None and value > 1 for value in (bid, ask)) else Decimal('1')
        def quote(value):
            value = number(value)
            return float(value / scale) if value is not None and 0 <= value / scale <= 1 and same_market else None
        seconds = number(row.get('seconds_remaining')) if same_market else None
        target = number(row.get('target_price')) if kind == 'recorded' and same_market else None
        if target is not None and (target <= 0 or scalar(target) is None):
            target = None
        decision, reason, strategy = row.get('decision', ''), row.get('reason', ''), row.get('strategy_name', '')
        if kind == 'market' and same_market and seconds is not None:
            matches = [(stamp, difference, shadow) for stamp, difference, shadow in shadows.get(seconds, []) if 0 <= at - stamp <= 2]
            candidates = {btc - difference for _, difference, _ in matches if difference is not None}
            targets.update(candidates)
            if len(candidates) == 1:
                target = candidates.pop()
            decisions = {(shadow.get('decision', ''), shadow.get('reason', ''), shadow.get('strategy_name', '')) for _, _, shadow in matches}
            if len(decisions) == 1:
                decision, reason, strategy = decisions.pop()
            elif len(decisions) > 1:
                decision, reason = 'Ambiguous', 'Concurrent bot observations disagree; the exact source is unknown.'
        if target is not None:
            targets.add(target)
        identity = (at, ticker, str(btc), str(bid), str(ask))
        if identity in seen:
            continue
        seen.add(identity)
        yes_bid, yes_ask = quote(bid), quote(ask)
        points.append(dict(time=at * 1000, timestamp=iso(at), btcPrice=btc_value, ticker=ticker,
            yesBid=yes_bid, yesAsk=yes_ask, noBid=quote(row.get('no_bid')) if kind == 'recorded' else None if yes_ask is None else 1 - yes_ask,
            noAsk=quote(row.get('no_ask')) if kind == 'recorded' else None if yes_bid is None else 1 - yes_bid,
            secondsRemaining=scalar(seconds),
            targetPrice=scalar(target), decision=decision if same_market else '',
            reason=reason if same_market else '', strategy=strategy if same_market else '',
            source=Path(source).name, runId=row.get('run_id', '')))
    points.sort(key=lambda point: point['time'])
    target = scalar(next(iter(targets))) if len(targets) == 1 else None
    if len(targets) > 1:
        notes.append('Target observations conflict. A target line and BTC-distance values are omitted.')
        for point in points:
            point['targetPrice'] = None
    for point in points:
        if target is not None and point['ticker'] == entry['ticker'] and point['targetPrice'] is None:
            point['targetPrice'] = target
        point['priceDifference'] = point['btcPrice'] - point['targetPrice'] if point['targetPrice'] is not None else None
    if basis == 'shared':
        notes.append('Historical shared logs do not identify the exact bot. Target values and bid complements are reconstructed where possible; decisions may come from another bot.')
    if any(point['ticker'] != entry['ticker'] for point in points):
        notes.append('BTC samples may continue into another market; contract quotes are shown only for this trade’s ticker.')
    times = sorted(set(point['time'] / 1000 for point in points))
    intervals = [right - left for left, right in zip(times, times[1:]) if right > left]
    cadence = statistics.median(intervals) if intervals else None
    gap_limit = min(30, max(15, (cadence or 5) * 2.5))
    start, end = (entry['at'] - 120 if start is None else start), (entry['at'] + 120 if end is None else end)
    edges = [start, *times, end]
    gaps = [dict(start=left * 1000, end=right * 1000) for left, right in zip(edges, edges[1:]) if right - left > gap_limit]
    if not points:
        notes.append('No BTC observations were recorded in this window. Restart updated bots to record future replays.')
    elif gaps:
        notes.append('Some of the requested window was not recorded. Missing intervals are shaded and are not filled in.')
    return dict(points=points, sourceBasis=basis, notes=notes, targetPrice=target, targetBasis='recorded' if basis == 'recorded' else 'inferred',
        coverage=dict(samples=len(points), firstAt=iso(times[0]) if times else None, lastAt=iso(times[-1]) if times else None,
            typicalSeconds=round(cadence, 2) if cadence else None, gaps=gaps))


class ReplayService:
    def __init__(self, root):
        self.root = Path(root)
        self.index = ReplayIndex(self.root / 'data' / 'replay_index.sqlite3')
        self.lock = threading.Lock()
        self.worker = None
        self.signature = None
        self.finished = 0
        self.state = {'status': 'idle'}

    def prepare(self, sources, *, refresh=False):
        signature = tuple((str(path), path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns) for path, _ in sources)
        with self.lock:
            if self.worker and self.worker.is_alive():
                return dict(self.state)
            known_sources = {item[0] for item in self.signature or ()}
            same_sources = {item[0] for item in signature} <= known_sources
            if self.state['status'] == 'ready' and not refresh and (signature == self.signature or (same_sources and time.monotonic() - self.finished < 10)):
                return {'status': 'ready'}
            self.state = {'status': 'preparing', 'rows': 0, 'files': 0, 'totalFiles': len(sources)}
            def progress(**values):
                with self.lock:
                    self.state.update(values)
            def work():
                try:
                    self.index.update(sources, progress)
                    with self.lock:
                        self.signature, self.finished = signature, time.monotonic()
                        self.state = {'status': 'ready'}
                except Exception as exc:
                    with self.lock:
                        self.state = {'status': 'error', 'message': f'Could not prepare replay data: {exc}'}
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()
            return dict(self.state)

    def replay(self, bot_id, trade_id, *, refresh=False, window='entry'):
        if window not in ('entry', 'market'):
            raise ValueError('Choose the full market or ±2-minute entry window')
        entry = locate_trade(self.root, bot_id, trade_id)
        start, end, basis = market_period(entry) if window == 'market' else (entry['at'] - 120, entry['at'] + 120, 'logged entry time')
        sources = observation_sources(self.root, entry['at'], start=start, end=end)
        state = self.prepare(sources, refresh=refresh)
        if state['status'] != 'ready':
            return state, 202 if state['status'] == 'preparing' else 500
        records, truncated = self.index.window(start, end, sources)
        result = normalize_window(records, entry, start=start, end=end)
        if window == 'market':
            result['notes'].append(f'Full 15-minute period resolved from {basis}.')
            if not start <= entry['at'] <= end:
                result['notes'].append('This order attempt was logged outside the market period; its marker is outside the chart.')
        if truncated:
            result['notes'].append('This window has more than 25,000 observations; only the first 25,000 are shown.')
        return dict(status='ready', window=window, entry=entry, startTime=start * 1000, endTime=end * 1000,
                    generatedAt=iso(time.time()), **result), 200
