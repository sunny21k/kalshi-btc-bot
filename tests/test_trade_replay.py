import csv
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import bot_telemetry
import dashboard
from replay_index import ReplayIndex, instant
from trade_replay import ReplayService, locate_trade, normalize_window, market_period, observation_sources

AT = instant('2026-11-06T20:55:50+00:00')
TICKER = 'KXBTC15M-26NOV061600-00'


def iso(at):
    return datetime.fromtimestamp(at, timezone.utc).isoformat()


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


class ReplayIndexTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'market.csv'
        self.index = ReplayIndex(self.root / 'index.sqlite3')

    def test_index_filters_window_preserves_original_files_and_updates_without_duplicates(self):
        fields = ['timestamp', 'ticker', 'btc_price']
        rows = [dict(timestamp=iso(AT + offset), ticker=TICKER, btc_price='100') for offset in (-121, -120, 0, 120, 121)]
        write_csv(self.path, fields, rows)
        before = self.path.read_bytes()
        self.index.update([(self.path, 'market')])
        records, truncated = self.index.window(AT - 120, AT + 120, [(self.path, 'market')])
        self.assertEqual(3, len(records)); self.assertFalse(truncated)
        self.assertEqual(before, self.path.read_bytes())
        self.index.update([(self.path, 'market')])
        self.assertEqual(3, len(self.index.window(AT - 120, AT + 120, [(self.path, 'market')])[0]))
        with self.path.open('a') as file:
            file.write(f'{iso(AT + 10)},{TICKER},101')
        self.index.update([(self.path, 'market')])
        self.assertEqual(3, len(self.index.window(AT - 120, AT + 120, [(self.path, 'market')])[0]))
        with self.path.open('a') as file:
            file.write('\n')
        self.index.update([(self.path, 'market')])
        self.assertEqual(4, len(self.index.window(AT - 120, AT + 120, [(self.path, 'market')])[0]))

    def test_log_replacement_discards_old_offsets_and_accepts_out_of_order_rows(self):
        fields = ['timestamp', 'ticker', 'btc_price']
        write_csv(self.path, fields, [dict(timestamp=iso(AT), ticker=TICKER, btc_price='100')])
        self.index.update([(self.path, 'market')])
        replacement = self.root / 'replacement.csv'
        write_csv(replacement, fields, [dict(timestamp=iso(AT + offset), ticker=TICKER, btc_price=str(offset)) for offset in (20, 5)])
        os.replace(replacement, self.path)
        self.index.update([(self.path, 'market')])
        records, _ = self.index.window(AT - 120, AT + 120, [(self.path, 'market')])
        self.assertEqual([AT + 5, AT + 20], [record[2] for record in records])


class ReplayNormalizationTests(unittest.TestCase):
    def entry(self):
        return dict(at=AT, botId='btc15_dual_live', ticker=TICKER, side='NO', anchorLabel='Order attempt')

    def record(self, offset, kind='market', **updates):
        row = dict(timestamp=iso(AT + offset), ticker=TICKER, btc_price='100', yes_bid='.20', yes_ask='.22', seconds_remaining='120')
        row.update(updates)
        return (f'{kind}.csv', kind, AT + offset, row)

    def test_legacy_quotes_and_target_are_reconstructed_without_claiming_exact_bot_source(self):
        records = [self.record(-5), self.record(5), self.record(-5.1, 'shadow', live_enabled='True',
            price_difference='-10', decision='BUY NO', reason='distance passed', strategy_name='rule')]
        result = normalize_window(records, self.entry())
        self.assertEqual('shared', result['sourceBasis'])
        self.assertEqual(110, result['targetPrice'])
        self.assertEqual(.8, result['points'][0]['noAsk'])
        self.assertAlmostEqual(.78, result['points'][0]['noBid'])
        self.assertEqual(-10, result['points'][1]['priceDifference'])
        self.assertEqual('BUY NO', result['points'][0]['decision'])
        self.assertIn('exact bot', ' '.join(result['notes']))

    def test_conflicting_targets_and_decisions_stay_unknown(self):
        rows = [self.record(0), self.record(-.1, 'shadow', live_enabled='True', price_difference='-10', decision='BUY NO', reason='a'),
                self.record(-.2, 'shadow', live_enabled='True', price_difference='-15', decision='WAIT', reason='b'),
                self.record(1, seconds_remaining='119'),
                self.record(.9, 'shadow', seconds_remaining='119', live_enabled='True', price_difference='-10', decision='WAIT', reason='later')]
        result = normalize_window(rows, self.entry())
        self.assertIsNone(result['targetPrice'])
        self.assertIsNone(result['points'][0]['priceDifference'])
        self.assertEqual('Ambiguous', result['points'][0]['decision'])
        self.assertTrue(all(point['priceDifference'] is None for point in result['points']))

    def test_own_bot_recordings_take_priority_and_quotes_do_not_cross_market_rollovers(self):
        rows = [self.record(0), self.record(-10, 'recorded', bot_id='btc15_dual_live', target_price='110', no_bid='.78', no_ask='.8'),
                self.record(10, 'recorded', bot_id='btc15_dual_live', ticker='NEXT', target_price='120', no_bid='.7', no_ask='.8'),
                self.record(0, 'recorded', bot_id='btc15_dual_paper', btc_price='900')]
        result = normalize_window(rows, self.entry())
        self.assertEqual('recorded', result['sourceBasis'])
        self.assertEqual(2, len(result['points']))
        self.assertIsNone(result['points'][1]['noAsk'])
        self.assertIsNone(result['points'][1]['priceDifference'])
        self.assertEqual(100, result['points'][1]['btcPrice'])

    def test_missing_intervals_and_invalid_prices_are_not_filled(self):
        result = normalize_window([self.record(-100), self.record(100), self.record(0, btc_price='NaN'), self.record(1, btc_price='1e1000')], self.entry())
        self.assertEqual(2, len(result['points']))
        self.assertTrue(result['coverage']['gaps'])
        empty = normalize_window([], self.entry())
        self.assertEqual([], empty['points'])
        self.assertIn('No BTC observations', ' '.join(empty['notes']))


class ReplayServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        write_csv(self.root / 'data/live_trades.csv', ['timestamp', 'trade_id', 'bot_id', 'ticker', 'side', 'filled_count', 'entry_price'],
                  [dict(timestamp=iso(AT), trade_id='live-test', bot_id='btc15_dual_live', ticker=TICKER, side='NO', filled_count='0', entry_price='.8')])
        write_csv(self.root / 'data/market_data.csv', ['timestamp', 'ticker', 'btc_price', 'yes_bid', 'yes_ask', 'seconds_remaining'],
                  [dict(timestamp=iso(AT + offset), ticker=TICKER, btc_price=str(1000 + offset), yes_bid='.2', yes_ask='.22', seconds_remaining=str(120 - offset)) for offset in (-110, 0, 110)])

    def test_async_preparation_then_replay_is_read_only_and_unfilled_attempt_is_labeled(self):
        service = ReplayService(self.root)
        before = (self.root / 'data/live_trades.csv').read_bytes()
        result, code = service.replay('btc15_dual_live', 'live-test')
        self.assertEqual(202, code)
        service.worker.join(10)
        result, code = service.replay('btc15_dual_live', 'live-test')
        self.assertEqual(200, code)
        self.assertEqual(3, len(result['points']))
        self.assertFalse(result['entry']['filled'])
        self.assertEqual('Order attempt', result['entry']['anchorLabel'])
        self.assertEqual(before, (self.root / 'data/live_trades.csv').read_bytes())
        with self.assertRaises(LookupError):
            locate_trade(self.root, 'btc15_live', 'live-test')

    def test_scalp_replay_uses_original_open_time_not_close_time(self):
        write_csv(self.root / 'data/scalp_paper_trades.csv', ['timestamp', 'trade_id', 'ticker', 'side', 'event'],
                  [dict(timestamp=iso(AT + 60), trade_id='scalp-test', ticker=TICKER, side='NO', event='CLOSE'),
                   dict(timestamp=iso(AT), trade_id='scalp-test', ticker=TICKER, side='NO', event='OPEN')])
        self.assertEqual(AT, locate_trade(self.root, 'scalp_paper', 'scalp-test')['at'])

    def test_full_market_window_covers_start_to_close_and_keeps_entry_window(self):
        fields = ['timestamp', 'ticker', 'btc_price', 'yes_bid', 'yes_ask', 'seconds_remaining']
        write_csv(self.root / 'data/market_data.csv', fields,
            [dict(timestamp=iso(AT + offset), ticker=TICKER, btc_price=str(1000 + offset), yes_bid='.2', yes_ask='.22', seconds_remaining=str(250 - offset))
             for offset in (-700, -600, -110, 0, 110, 200, 300)])
        service = ReplayService(self.root)
        result, code = service.replay('btc15_dual_live', 'live-test', window='market')
        self.assertEqual(202, code); service.worker.join(10)
        result, code = service.replay('btc15_dual_live', 'live-test', window='market')
        self.assertEqual(200, code)
        self.assertEqual('market', result['window'])
        self.assertEqual(900000, result['endTime'] - result['startTime'])
        self.assertEqual(instant('2026-11-06T20:45:00+00:00') * 1000, result['startTime'])
        self.assertEqual(instant('2026-11-06T21:00:00+00:00') * 1000, result['endTime'])
        self.assertEqual(5, len(result['points']))
        self.assertGreater(result['entry']['at'] * 1000, result['startTime'])
        close_up, code = service.replay('btc15_dual_live', 'live-test', window='entry')
        self.assertEqual(200, code)
        self.assertEqual(240000, close_up['endTime'] - close_up['startTime'])
        self.assertEqual(3, len(close_up['points']))

    def test_new_source_file_is_prepared_even_during_the_recent_cache_interval(self):
        service = ReplayService(self.root)
        service.replay('btc15_dual_live', 'live-test'); service.worker.join(10)
        path = self.root / 'data/replay/btc15_dual_live/2026-11-06.jsonl'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(timestamp=iso(AT), bot_id='btc15_dual_live', ticker=TICKER, btc_price='1000', target_price='1010')) + '\n')
        result, code = service.replay('btc15_dual_live', 'live-test', window='market')
        self.assertEqual(202, code); service.worker.join(10)
        result, code = service.replay('btc15_dual_live', 'live-test', window='market')
        self.assertEqual(200, code)
        self.assertEqual('recorded', result['sourceBasis'])

    def test_unsupported_window_is_rejected_without_preparing_data(self):
        service = ReplayService(self.root)
        with self.assertRaises(ValueError):
            service.replay('btc15_dual_live', 'live-test', window='whole-day')
        self.assertIsNone(service.worker)

    def test_get_endpoint_only_reads_replay_and_rejects_unknown_bot(self):
        handler = SimpleNamespace(path='/api/trades/replay?botId=btc15_dual_live&tradeId=live-test')
        with patch.object(dashboard, 'ROOT', self.root), patch.object(dashboard, 'REPLAY_SERVICES', {}), patch.object(dashboard, 'json_response') as response, patch.object(dashboard, 'start_bot') as start, patch.object(dashboard, 'refresh_results') as refresh:
            dashboard.DashboardHandler.do_GET(handler)
            self.assertEqual(202, response.call_args.kwargs['status'])
            service = dashboard.REPLAY_SERVICES[str(self.root)]
            service.worker.join(10)
            start.assert_not_called(); refresh.assert_not_called()
            self.assertEqual(400, dashboard.replay_response({'botId': ['../secret'], 'tradeId': ['live-test']})[1])

    def test_endpoint_forwards_the_full_market_window(self):
        service = SimpleNamespace(replay=lambda *args, **kwargs: (kwargs, 200))
        with patch.object(dashboard, 'ROOT', self.root), patch.object(dashboard, 'REPLAY_SERVICES', {str(self.root): service}):
            result, code = dashboard.replay_response({'botId': ['btc15_dual_live'], 'tradeId': ['live-test'], 'window': ['market']})
        self.assertEqual(200, code)
        self.assertEqual('market', result['window'])

    def test_new_capture_is_per_bot_and_does_not_raise_when_disk_is_unavailable(self):
        with patch.object(bot_telemetry, 'STATUS_DIR', self.root / 'status'), patch.object(bot_telemetry, 'REPLAY_DIR', self.root / 'replay'):
            reporter = bot_telemetry.BotTelemetry('btc15_dual_live')
            reporter.price(Decimal('100'))
            reporter.market(ticker=TICKER, targetPrice='110', yesAsk='.22', noAsk='.8', secondsRemaining=120)
            reporter.decide('BUY NO', 'distance passed', side='NO', strategy='rule')
            reporter.replay(yes_bid='.2', no_bid='.78')
            files = list((self.root / 'replay/btc15_dual_live').glob('*.jsonl'))
            self.assertEqual(1, len(files))
            row = json.loads(files[0].read_text())
            self.assertEqual('btc15_dual_live', row['bot_id'])
            self.assertEqual('100', row['btc_price'])
            self.assertEqual('BUY NO', row['decision'])
            with patch('pathlib.Path.open', side_effect=OSError('disk unavailable')):
                reporter.replay(yes_bid='.2', no_bid='.78')


class MarketPeriodTests(unittest.TestCase):
    def test_ticker_dates_and_dst_folds_resolve_against_the_logged_entry(self):
        for ticker, at, close in (
            (TICKER, '2026-11-06T20:55:50+00:00', '2026-11-06T21:00:00+00:00'),
            ('KXBTC15M-26OCT092145-45', '2026-10-10T01:42:00+00:00', '2026-10-10T01:45:00+00:00'),
            ('KXBTC15M-26NOV010115-15', '2026-11-01T05:11:00+00:00', '2026-11-01T05:15:00+00:00'),
            ('KXBTC15M-26NOV010115-15', '2026-11-01T06:11:00+00:00', '2026-11-01T06:15:00+00:00'),
        ):
            with self.subTest(ticker=ticker, at=at):
                start, end, _ = market_period({'ticker': ticker, 'at': instant(at)})
                self.assertEqual(instant(close), end)
                self.assertEqual(900, end - start)

    def test_recorded_close_and_countdown_can_resolve_without_a_parseable_ticker(self):
        end = instant('2026-11-06T21:00:00Z')
        for details in ({'marketCloseTime': '2026-11-06T21:00:00Z'}, {'secondsRemainingAtEntry': end - AT}):
            start, close, _ = market_period(dict(ticker='UNAVAILABLE', at=AT, **details))
            self.assertEqual(end, close); self.assertEqual(900, close - start)
        with self.assertRaises(ValueError):
            market_period(dict(ticker='UNKNOWN', at=AT))
        with self.assertRaises(ValueError):
            market_period(dict(ticker='KXBTC15M-26MAR080215-15', at=instant('2026-03-08T07:11:00Z')))

    def test_full_period_loads_both_utc_daily_logs_at_midnight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for date in ('2026-11-06', '2026-11-07'):
                path = root / f'data/replay/btc15_dual_live/{date}.jsonl'
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text('')
            close = instant('2026-11-07T00:00:00Z')
            sources = observation_sources(root, close - 100, start=close - 900, end=close)
            self.assertEqual({'2026-11-06.jsonl', '2026-11-07.jsonl'}, {path.name for path, kind in sources})


if __name__ == '__main__':
    unittest.main()
