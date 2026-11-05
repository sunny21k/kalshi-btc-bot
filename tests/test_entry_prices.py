import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import DEFAULT, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import bot
import bot_rules
import dashboard
from bot_settings import saved_entry_price_range, save_entry_price_range
from direction_strategy import make_direction_paper_decision
from entry_prices import MIN_ENV, MAX_ENV, entry_price_range_from_env, serialize_entry_price_range
from scalp_strategy import build_candle, choose_scalp_entry
from strategy import make_dual_live_decision, make_late_momentum_decision


CUSTOM = {'min': '0.7000', 'max': '0.9000'}


class EntryPriceValidationTests(unittest.TestCase):
    def test_valid_range_and_exact_boundaries_and_environment(self):
        self.assertEqual({'min': '0.7525', 'max': '0.9000'}, serialize_entry_price_range({'min': '.7525', 'max': '.90'}))
        self.assertEqual({'min': '0.7500', 'max': '0.7500'}, serialize_entry_price_range({'min': '.75', 'max': '.75'}))
        with patch.dict(os.environ, {MIN_ENV: '.7', MAX_ENV: '.9'}):
            self.assertEqual(CUSTOM, serialize_entry_price_range(entry_price_range_from_env()))
        with patch.dict(os.environ, {MIN_ENV: '', MAX_ENV: ''}):
            self.assertIsNone(entry_price_range_from_env())

    def test_bad_values_and_one_sided_environment_are_rejected(self):
        for value in ({}, [], '75-90', {'min': '0.9', 'max': '0.75'},
                      *({'min': v, 'max': '.9'} for v in ('', 'NaN', 'Infinity', '0', '-1', '1', '0.75001', True)),
                      {'min': '.75', 'max': '1'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                serialize_entry_price_range(value)
        with patch.dict(os.environ, {MIN_ENV: '.7', MAX_ENV: ''}), self.assertRaises(ValueError):
            entry_price_range_from_env()

    def test_saved_settings_survive_reloads_and_remain_separate_for_each_bot(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(saved_entry_price_range(root, 'btc15_paper'))
            save_entry_price_range(root, 'btc15_paper', CUSTOM)
            save_entry_price_range(root, 'btc15_dual_live', {'min': '.8', 'max': '.92'})
            self.assertEqual(CUSTOM, saved_entry_price_range(root, 'btc15_paper'))
            self.assertEqual('0.8000', saved_entry_price_range(root, 'btc15_dual_live')['min'])
            save_entry_price_range(root, 'btc15_paper', None)
            self.assertIsNone(saved_entry_price_range(root, 'btc15_paper'))
            self.assertEqual('0.8000', saved_entry_price_range(root, 'btc15_dual_live')['min'])
            self.assertEqual([], list((Path(root) / 'data').glob('.bot-settings-*')))


class EntryPriceStrategyTests(unittest.TestCase):
    def signal(self, side, *, price='.72', seconds=270, distance=60, custom=CUSTOM, **kwargs):
        prices = [1000 + distance - 3, 1000 + distance - 2, 1000 + distance - 1, 1000 + distance] if side == 'YES' else [1000 - distance + 3, 1000 - distance + 2, 1000 - distance + 1, 1000 - distance]
        return make_dual_live_decision(btc_price=prices[-1], target_price=1000, seconds_remaining=seconds,
            yes_ask=price, no_ask=price, spread=kwargs.pop('spread', '.02'), recent_prices=prices,
            confirmation_count=3, entry_price_range=custom, **kwargs)

    def test_custom_range_replaces_both_rule_bands_and_defaults_remain_distinct(self):
        for side in ('YES', 'NO'):
            for seconds, distance in ((270, 60), (180, 20)):
                for price in ('.70', '.75', '.90'):
                    self.assertEqual(f'BUY {side}', self.signal(side, price=price, seconds=seconds, distance=distance)['decision'])
                for price in ('.6999', '.9001'):
                    self.assertEqual('WAIT', self.signal(side, price=price, seconds=seconds, distance=distance)['decision'])
            self.assertEqual('WAIT', self.signal(side, price='.79', custom=None)['decision'])
            self.assertEqual(f'BUY {side}', self.signal(side, price='.79', custom=None, seconds=180, distance=20)['decision'])
            self.assertEqual('WAIT', self.signal(side, price='.90', custom=None, seconds=180, distance=20)['decision'])
            self.assertEqual('WAIT', self.signal(side, spread='.04')['decision'])
            self.assertEqual('WAIT', self.signal(side, seconds=30)['decision'])

    def test_all_15m_runners_receive_range_and_record_its_snapshot_without_exchange_requests(self):
        for bot_id in dashboard.BOTS:
            if bot_id == 'scalp_paper':
                continue
            live = 'live' in bot_id
            decision = make_direction_paper_decision if 'direction' in bot_id else make_dual_live_decision if bot_id == 'btc15_dual_live' else make_late_momentum_decision
            for price, allowed in (('.72', True), ('.91', False)):
                with self.subTest(bot=bot_id, price=price), patch.dict(os.environ, {MIN_ENV: '.7', MAX_ENV: '.9'}), patch.multiple(bot,
                    BotTelemetry=DEFAULT, get_btc_price=DEFAULT, get_current_market=DEFAULT,
                    get_seconds_remaining=DEFAULT, get_orderbook=DEFAULT, get_yes_quote=DEFAULT,
                    log_market_data=DEFAULT, log_shadow_signal=DEFAULT, record_paper_trade=DEFAULT,
                    place_live_trade=DEFAULT) as mocks, patch('bot.time.sleep', side_effect=[None] * 3 + [KeyboardInterrupt]), redirect_stdout(io.StringIO()):
                    mocks['get_btc_price'].side_effect = [940, 938, 936, 934]
                    mocks['get_current_market'].return_value = {'ticker': 'TEST', 'floor_strike': '1000'}
                    mocks['get_seconds_remaining'].return_value = 270
                    mocks['get_yes_quote'].return_value = tuple(Decimal(v) for v in ('.10', '.12', str(Decimal(price) - Decimal('.02')), price, '.02'))
                    bot.main(live_enabled=live, paper_sides=('NO',) if bot_id == 'btc15_paper' else ('YES', 'NO'),
                        paper_bot_id=bot_id, live_bot_id=bot_id, decision_fn=decision, enable_early_up=bot_id == 'btc15_live')
                    execution = mocks['place_live_trade' if live else 'record_paper_trade']
                    self.assertEqual(allowed, execution.called)
                    self.assertEqual(CUSTOM, mocks['BotTelemetry'].call_args.kwargs['settings']['entryPriceRange'])
                    self.assertFalse(mocks['record_paper_trade' if live else 'place_live_trade'].called)

    def test_scalp_range_and_displayed_rules_use_the_same_selected_bounds(self):
        candles = [build_candle(i * 5, [100 + i * 3, 102 + i * 3]) for i in range(3)]
        for price, expected in (('.69', 'WAIT'), ('.7', 'BUY YES'), ('.9', 'BUY YES'), ('.91', 'WAIT')):
            signal = choose_scalp_entry(candles, [build_candle(0, [100, 110])], yes_ask=price,
                no_ask='.2', spread='.02', entry_price_range=CUSTOM)
            self.assertEqual(expected, signal['decision'])
        for bot_id in dashboard.BOTS:
            profile = bot_rules.build_bot_rules(bot_id, settings={'entryPriceRange': CUSTOM})
            labels = ('Ask band',) if bot_id == 'scalp_paper' else ('5-minute rule', '4-minute rule')
            for label in labels:
                detail = next(item['detail'] for section in profile['sections'] for item in section['items'] if item['label'] == label)
                self.assertIn('70¢–90¢', detail)

    def test_early_entry_can_use_custom_prices_without_bypassing_direction_checks(self):
        args = dict(btc_price=1080, target_price=1000, seconds_remaining=400, yes_ask='.72', no_ask='.72',
                    spread='.02', recent_prices=[1077, 1078, 1079, 1080], confirmation_count=3)
        self.assertEqual('WAIT', make_late_momentum_decision(**args)['decision'])
        self.assertEqual('BUY YES', make_late_momentum_decision(**args, entry_price_range=CUSTOM)['decision'])
        # Normal momentum agrees, but one of the three moves is opposite.
        args.update(seconds_remaining=270, recent_prices=[1077, 1079, 1078, 1080])
        self.assertEqual('WAIT', make_direction_paper_decision(**args, entry_price_range=CUSTOM)['decision'])


class DashboardEntryPriceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        patches = patch.multiple(dashboard, ROOT=self.root, LOG_DIR=self.root / 'logs',
            BOT_PROCESSES={}, BOT_TRADE_BUDGETS={}, BOT_DAILY_LIVE_LIMITS={}, BOT_ENTRY_PRICE_RANGES={})
        patches.start()
        self.addCleanup(patches.stop)

    def test_each_child_receives_only_its_own_saved_range_and_defaults_clear_inherited_values(self):
        for bot_id in dashboard.BOTS:
            dashboard.BOT_PROCESSES.clear()
            process = Mock(pid=12345)
            process.poll.return_value = None
            with self.subTest(bot=bot_id), patch('dashboard.subprocess.Popen', return_value=process) as launch, patch('dashboard.time.sleep'), redirect_stdout(io.StringIO()):
                self.assertEqual(200, dashboard.start_bot(bot_id, entry_price_range=CUSTOM)[1])
                self.assertEqual('0.7000', launch.call_args.kwargs['env'][MIN_ENV])
                self.assertEqual('0.9000', launch.call_args.kwargs['env'][MAX_ENV])
                self.assertEqual(CUSTOM, saved_entry_price_range(self.root, bot_id))
                dashboard.BOT_PROCESSES.clear()
                self.assertEqual(200, dashboard.start_bot(bot_id)[1])
                self.assertEqual('0.7000', launch.call_args.kwargs['env'][MIN_ENV])
                dashboard.BOT_PROCESSES.clear()
                with patch.dict(os.environ, {MIN_ENV: '.2', MAX_ENV: '.3'}):
                    self.assertEqual(200, dashboard.start_bot(bot_id, entry_price_range=None)[1])
                self.assertEqual('', launch.call_args.kwargs['env'][MIN_ENV])
                self.assertEqual('', launch.call_args.kwargs['env'][MAX_ENV])

    def test_invalid_range_never_launches_and_running_range_cannot_be_changed(self):
        with patch('dashboard.subprocess.Popen') as launch:
            self.assertEqual(400, dashboard.start_bot('btc15_dual_live', entry_price_range={'min': '.9', 'max': '.75'})[1])
            launch.assert_not_called()
        process = Mock(pid=12345)
        process.poll.return_value = None
        dashboard.BOT_PROCESSES['btc15_dual_live'] = process
        dashboard.BOT_ENTRY_PRICE_RANGES['btc15_dual_live'] = CUSTOM
        with patch('dashboard.subprocess.Popen') as launch:
            result, status = dashboard.start_bot('btc15_dual_live', entry_price_range=None)
            self.assertEqual(409, status)
            self.assertIn('Stop the bot', result['message'])
            launch.assert_not_called()

    def test_status_restores_saved_range_and_defaults_for_every_bot(self):
        save_entry_price_range(self.root, 'btc15_dual_live', CUSTOM)
        with patch.object(dashboard, 'runtime_status', side_effect=lambda *args, **kwargs: {'state': 'stopped', 'processAlive': False, 'blockers': []}):
            statuses = {row['id']: row for row in dashboard.bot_statuses()}
        self.assertEqual(CUSTOM, statuses['btc15_dual_live']['entryPriceRange'])
        self.assertIsNone(statuses['btc15_dual_paper']['entryPriceRange'])
        for row in statuses.values():
            self.assertTrue(row['supportsEntryPriceRange'])
            self.assertTrue(row['entryPriceDefaults'])

    def test_post_handler_distinguishes_saved_preference_from_explicit_reset(self):
        for setting in ({}, {'entryPriceRange': None}, {'entryPriceRange': CUSTOM}):
            body = json.dumps({'botId': 'btc15_dual_live', **setting}).encode()
            handler = SimpleNamespace(path='/api/bots/start', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
            with patch.object(dashboard, 'start_bot', return_value=({'ok': True}, 200)) as start, patch.object(dashboard, 'json_response'):
                dashboard.DashboardHandler.do_POST(handler)
            expected = {'trade_budget': None, 'daily_live_order_limit': None}
            if setting:
                expected['entry_price_range'] = setting['entryPriceRange']
            start.assert_called_once_with('btc15_dual_live', **expected)

    def test_settings_write_failure_never_launches_an_order_process(self):
        with patch.object(dashboard, 'save_entry_price_range', side_effect=OSError('disk unavailable')), patch('dashboard.subprocess.Popen') as launch:
            self.assertEqual(500, dashboard.start_bot('btc15_dual_live', entry_price_range=CUSTOM)[1])
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
