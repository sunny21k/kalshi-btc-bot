import csv
import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import backtest_direction as backtest


def sample(index, price, *, stamp=None, ticker='T', target=1000, yes_ask='0.22', no_ask='0.80'):
    stamp = index * 5 if stamp is None else stamp
    at = datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(seconds=stamp)
    return dict(stamp=stamp, timestamp=at.isoformat(), ticker=ticker,
                btc_price=Decimal(str(price)), target_price=Decimal(str(target)) if target is not None else None,
                seconds_remaining=Decimal(300 - index * 5), yes_ask=Decimal(yes_ask),
                no_ask=Decimal(no_ask), spread=Decimal('0.02'))


class ReplayTests(unittest.TestCase):
    def test_live_minimum_comparison_blocks_cheap_strong_entries_and_can_enter_later(self):
        tape = [sample(index, price, no_ask='0.79' if index < 4 else '0.80')
                for index, price in enumerate([940, 938, 936, 934, 932, 930])]
        trades = backtest.replay(tape, {'T': 'NO'}, comparison='strong-min-80')
        before = next(row for row in trades if row['variant'] == 'original')
        after = next(row for row in trades if row['variant'] == 'live_80c')
        self.assertEqual('0.79', before['entry_price'])
        self.assertEqual('0.80', after['entry_price'])
        self.assertGreater(after['timestamp'], before['timestamp'])

    def test_current_rules_and_direction_filter_enter_on_different_valid_polls(self):
        tape = [sample(index, price) for index, price in enumerate([940, 930, 934, 932, 931, 930, 929])]
        trades = backtest.replay(tape, {'T': 'NO'})
        self.assertEqual(['original', 'direction'], [row['variant'] for row in trades])
        self.assertLess(trades[0]['timestamp'], trades[1]['timestamp'])
        self.assertEqual('strong_5m_50_direction', trades[1]['strategy_name'])
        prices = list(map(Decimal, json.loads(trades[1]['recent_prices'])))
        self.assertTrue(all(right < left for left, right in zip(prices, prices[1:])))

    def test_one_entry_per_market_even_after_the_side_reverses(self):
        prices = [940, 938, 936, 934, 1060, 1062, 1064, 1066]
        trades = backtest.replay([sample(index, price) for index, price in enumerate(prices)], {'T': 'NO'})
        self.assertEqual(2, len(trades))
        self.assertTrue(all(row['side'] == 'NO' for row in trades))

    def test_sample_interval_prevents_multiple_bots_from_faking_three_moves(self):
        tape = [sample(index, price, stamp=stamp) for index, (stamp, price) in enumerate(
            [(0, 940), (0.1, 939), (0.2, 938), (5, 938), (5.1, 937), (10, 936), (15, 934)])]
        quality = Counter()
        trades = backtest.replay(tape, {'T': 'NO'}, quality=quality)
        self.assertEqual(4, quality['sampled_observations'])
        self.assertEqual(3, quality['subinterval_rows_skipped'])
        observed = next(row for row in trades if row['variant'] == 'direction')
        self.assertEqual(['940', '938', '936', '934'], json.loads(observed['recent_prices']))

    def test_gap_resets_history_and_confirmations(self):
        tape = [sample(index, price, stamp=stamp) for index, (stamp, price) in enumerate(
            [(0, 940), (5, 938), (100, 936), (105, 934), (110, 932), (115, 930)])]
        quality = Counter()
        trades = backtest.replay(tape, {'T': 'NO'}, quality=quality)
        self.assertEqual(1, quality['gap_resets'])
        new = next(row for row in trades if row['variant'] == 'direction')
        self.assertEqual(['936', '934', '932', '930'], json.loads(new['recent_prices']))

    def test_settlements_never_change_entry_decisions_and_unknown_results_stay_pending(self):
        tape = [sample(index, price) for index, price in enumerate([940, 938, 936, 934])]
        won = backtest.replay(tape, {'T': 'NO'}, cost_per_contract='0.01')
        lost = backtest.replay(tape, {'T': 'YES'})
        pending = backtest.replay(tape, {})
        for left, right in zip(won, lost):
            for key in ('timestamp', 'side', 'entry_price', 'contracts', 'strategy_name'):
                self.assertEqual(left[key], right[key])
        self.assertEqual('25.0000', won[1]['gross_profit_loss'])
        self.assertEqual('23.7500', won[1]['net_profit_loss'])
        self.assertEqual('-100.0000', lost[1]['gross_profit_loss'])
        self.assertEqual('', pending[1]['net_profit_loss'])
        self.assertEqual(2, backtest.summarize(pending)['pending'])
        self.assertIsNone(backtest.summarize(pending)['gross_roi_pct'])

    def test_budget_uses_whole_contracts_and_does_not_reuse_old_trade_profit(self):
        tape = [sample(index, price, no_ask='0.83') for index, price in enumerate([940, 938, 936, 934])]
        row = backtest.replay(tape, {'T': 'NO'})[1]
        self.assertEqual(120, row['contracts'])
        self.assertEqual('99.6000', row['cost'])
        self.assertEqual('20.4000', row['gross_profit_loss'])

    def test_future_prices_cannot_change_an_earlier_entry(self):
        tape = [sample(index, price) for index, price in enumerate([940, 938, 936, 934])]
        first = backtest.replay(tape, {'T': 'NO'})
        longer = backtest.replay(tape + [sample(4, 1100), sample(5, 1200)], {'T': 'NO'})
        self.assertEqual(first, longer)

    def test_late_rule_is_preserved_and_missing_targets_cannot_be_reconstructed_from_outcomes(self):
        late = [dict(sample(index, price), seconds_remaining=Decimal(200)) for index, price in enumerate([990, 988, 986])]
        trades = backtest.replay(late, {'T': 'NO'})
        self.assertEqual(2, len(trades))
        self.assertTrue(all(row['strategy_name'] == 'late_4m_10' for row in trades))
        unknown = [sample(index, price, target=None) for index, price in enumerate([940, 938, 936, 934])]
        self.assertEqual([], backtest.replay(unknown, {'T': 'NO'}))

    def test_both_sides_have_the_same_direction_requirement(self):
        tape = [sample(index, price, yes_ask='0.80', no_ask='0.22') for index, price in enumerate([1060, 1062, 1064, 1066])]
        row = next(row for row in backtest.replay(tape, {'T': 'YES'}) if row['variant'] == 'direction')
        self.assertEqual('YES', row['side'])
        self.assertEqual('25.0000', row['gross_profit_loss'])

    def test_invalid_sampling_and_friction_settings_cannot_change_replay_semantics(self):
        for arguments in ({'sample_seconds': 0}, {'sample_seconds': float('nan')},
                          {'max_gap_seconds': float('inf')}, {'max_gap_seconds': 1},
                          {'cost_per_contract': '-1'}, {'cost_per_contract': 'NaN'}):
            with self.assertRaises(ValueError):
                backtest.replay([], {}, **arguments)


class DataPreparationTests(unittest.TestCase):
    def test_frozen_inputs_ignore_later_appends_and_drop_an_incomplete_final_row(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.csv'
            frozen = Path(directory) / 'frozen.csv'
            source.write_bytes(b'timestamp,ticker\n2026-11-05T20:00:00Z,T\npartial')
            _, metadata = backtest.freeze_input(source, frozen)
            self.assertEqual(b'timestamp,ticker\n2026-11-05T20:00:00Z,T\n', frozen.read_bytes())
            with source.open('ab') as file:
                file.write(b' row\n2026-11-05T20:00:01Z,T\n')
            self.assertEqual(1, len(list(backtest.rows(frozen))))
            self.assertEqual(frozen.stat().st_size, metadata['snapshot_bytes'])

    def test_concurrent_write_order_is_repaired_and_late_or_invalid_rows_are_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'market.csv'
            with path.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=['timestamp'])
                writer.writeheader()
                for seconds in (0, 2, 1, 10, 1, 12):
                    writer.writerow({'timestamp': (datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat()})
                writer.writerow({'timestamp': 'invalid'})
            quality = Counter()
            ordered = list(backtest.chronological(path, quality))
            self.assertEqual(sorted(row[0] for row in ordered), [row[0] for row in ordered])
            self.assertEqual(5, len(ordered))
            self.assertEqual(1, quality['late_rows_discarded'])
            self.assertEqual(1, quality['invalid_timestamps'])

    def test_targets_use_only_same_countdown_observations_available_at_the_time(self):
        quality = Counter()
        resolver = backtest.TargetResolver(iter([(10, dict(ticker='T', seconds_remaining='300', price_difference='-60'))]), quality)
        self.assertIsNone(resolver.resolve(9, 'T', Decimal(300), Decimal(940)))
        self.assertEqual(Decimal(1000), resolver.resolve(10, 'T', Decimal(300), Decimal(940)))
        self.assertEqual(Decimal(1000), resolver.resolve(20, 'T', Decimal(290), Decimal(930)))
        self.assertIsNone(resolver.resolve(20, 'OTHER', Decimal(290), Decimal(930)))

    def test_conflicting_targets_are_flagged_and_not_replaced_with_a_favorable_value(self):
        source = [(10, dict(ticker='T', seconds_remaining='300', price_difference='-60')),
                  (15, dict(ticker='T', seconds_remaining='295', price_difference='-50'))]
        resolver = backtest.TargetResolver(iter(source), Counter())
        self.assertEqual(Decimal(1000), resolver.resolve(10, 'T', Decimal(300), Decimal(940)))
        self.assertIsNone(resolver.resolve(15, 'T', Decimal(295), Decimal(940)))
        self.assertEqual({'T'}, resolver.conflicts)

    def test_complete_cli_is_offline_and_leaves_input_ledgers_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            markets, shadow, results = root / 'market.csv', root / 'shadow.csv', root / 'results.csv'
            observations = [sample(index, price) for index, price in enumerate([940, 938, 936, 934])]
            def write(path, data):
                with path.open('w', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=list(data[0]))
                    writer.writeheader()
                    writer.writerows(data)
            write(markets, [dict(timestamp=row['timestamp'], ticker='T', btc_price=str(row['btc_price']),
                                 seconds_remaining=str(row['seconds_remaining']), yes_bid='0.20', yes_ask='0.22', spread='0.02') for row in observations])
            write(shadow, [dict(timestamp=(datetime.fromisoformat(row['timestamp']) - timedelta(milliseconds=1)).isoformat(),
                                ticker='T', seconds_remaining=str(row['seconds_remaining']), price_difference=str(row['btc_price'] - 1000)) for row in observations])
            write(results, [dict(ticker='T', actual_result='NO', profit_loss='999999')])
            before = {path: path.read_bytes() for path in (markets, shadow, results)}
            with patch.object(sys, 'argv', ['backtest', '--market-data', str(markets), '--shadow-data', str(shadow), '--results', str(results), '--output-dir', str(root / 'reports')]), redirect_stdout(io.StringIO()):
                backtest.main()
            for path, content in before.items():
                self.assertEqual(content, path.read_bytes())
            summary = json.loads((root / 'reports' / 'summary.json').read_text())
            self.assertTrue(summary['approximation'])
            self.assertEqual('direction', summary['comparison_name'])
            self.assertEqual('25.0000', summary['comparison']['direction']['gross_profit_loss'])
            write(results, [dict(ticker='T', actual_result='YES'), dict(ticker='T', actual_result='NO')])
            outcomes, conflicts = backtest.recorded_outcomes([results])
            self.assertEqual({}, outcomes)
            self.assertEqual({'T'}, conflicts)


if __name__ == '__main__':
    unittest.main()
