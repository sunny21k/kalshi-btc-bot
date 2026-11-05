import copy
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
from bot_settings import configured_bot_preferences, default_bot_preferences, preferences_fingerprint, saved_entry_rules, save_entry_price_range
from direction_strategy import make_direction_paper_decision
from entry_rules import RULES_ENV, default_entry_rules, evaluate_entry_rules, filter_scalp_entry, validate_entry_rules, strategy_name
from strategy import make_dual_live_decision, make_late_momentum_decision


def custom_rule(**updates):
    rule = dict(id='custom-entry', name='Custom entry', enabled=True, maxMinutesLeft='3', minBtcDistance='7.5',
                side='BOTH', priceRange={'min': '.75', 'max': '.90'}, requireDirection=False)
    return validate_entry_rules([{**rule, **updates}])[0]


class EntryRuleTests(unittest.TestCase):
    def signal(self, rules, **updates):
        args = dict(entry_rules=rules, btc_price=992, target_price=1000, seconds_remaining=170,
                    yes_ask='.8', no_ask='.8', spread='.02', recent_prices=[995, 994, 993, 992], confirmation_count=3)
        return evaluate_entry_rules(**{**args, **updates})

    def test_custom_times_distances_sides_and_price_bands_are_used(self):
        rule = custom_rule()
        self.assertEqual('BUY NO', self.signal([rule])['decision'])
        for update in ({'seconds_remaining': 181}, {'btc_price': 993}, {'no_ask': '.91'}, {'spread': '.04'}, {'seconds_remaining': 30}):
            self.assertEqual('WAIT', self.signal([rule], **update)['decision'])
        self.assertEqual('WAIT', self.signal([custom_rule(side='YES')])['decision'])
        self.assertEqual('BUY YES', self.signal([custom_rule(side='YES')], btc_price=1008, recent_prices=[1005, 1006, 1007, 1008])['decision'])

    def test_priority_enable_disable_delete_and_direction_are_effective(self):
        first = custom_rule(priceRange={'min': '.85', 'max': '.9'})
        second = custom_rule(id='second')
        self.assertEqual('WAIT', self.signal([first, second])['decision'])
        self.assertEqual('BUY NO', self.signal([second, first])['decision'])
        self.assertEqual('BUY NO', self.signal([{**first, 'enabled': False}, second])['decision'])
        self.assertEqual('WAIT', self.signal([])['decision'])
        self.assertEqual('WAIT', self.signal([{**second, 'enabled': False}])['decision'])
        prices = [995, 993, 994, 992]
        self.assertEqual('BUY NO', self.signal([second], recent_prices=prices)['decision'])
        self.assertEqual('WAIT', self.signal([{**second, 'requireDirection': True}], recent_prices=prices)['decision'])
        result = make_direction_paper_decision(entry_rules=[second], btc_price=992, target_price=1000, seconds_remaining=170,
            yes_ask='.8', no_ask='.8', spread='.02', recent_prices=prices, confirmation_count=3)
        self.assertEqual('BUY NO', result['decision'])

    def test_default_rule_editor_matches_existing_strategy_decisions(self):
        for bot_id in ('btc15_dual_paper', 'btc15_direction_paper', 'btc15_live', 'btc15_dual_live'):
            decision = make_direction_paper_decision if 'direction' in bot_id else make_dual_live_decision if bot_id == 'btc15_dual_live' else make_late_momentum_decision
            for side in ('YES', 'NO'):
                for seconds, distance in ((180, 20), (270, 60), (450, 80)):
                    prices = [1000 + distance - 3, 1000 + distance - 2, 1000 + distance - 1, 1000 + distance] if side == 'YES' else [1000 - distance + 3, 1000 - distance + 2, 1000 - distance + 1, 1000 - distance]
                    for price in ('.74', '.75', '.79', '.8', '.85', '.9', '.92', '.93'):
                        args = dict(btc_price=prices[-1], target_price=1000, seconds_remaining=seconds, yes_ask=price,
                                    no_ask=price, spread='.02', recent_prices=prices, confirmation_count=3, enable_early_up=bot_id == 'btc15_live')
                        old = decision(**args)
                        new = decision(**args, entry_rules=default_entry_rules(bot_id))
                        with self.subTest(bot=bot_id, side=side, seconds=seconds, price=price):
                            self.assertEqual(old['decision'], new['decision'])
                            if old['decision'] != 'WAIT':
                                self.assertEqual(old['strategy_name'], new['strategy_name'])

    def test_rule_validation_rejects_invalid_inputs_without_silent_fallback(self):
        for update in ({'maxMinutesLeft': '16'}, {'maxMinutesLeft': 'NaN'}, {'maxMinutesLeft': '0'},
                       {'minBtcDistance': '-1'}, {'minBtcDistance': 'Infinity'}, {'enabled': 'false'},
                       {'requireDirection': 1}, {'side': 'DOWN'}, {'name': ''}, {'name': 'line\nbreak'},
                       {'priceRange': {'min': '.95', 'max': '.9'}}, {'unexpected': True}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_entry_rules([{**custom_rule(), **update}])
        with self.assertRaises(ValueError):
            validate_entry_rules([custom_rule(), custom_rule()])
        with self.assertRaises(ValueError):
            validate_entry_rules([custom_rule(side='YES')], 'btc15_paper')
        with self.assertRaises(ValueError):
            validate_entry_rules([custom_rule(id=f'rule-{i}') for i in range(21)])

    def test_edited_rules_have_distinct_history_names_and_details(self):
        rule = custom_rule()
        self.assertNotEqual(strategy_name(rule), strategy_name({**rule, 'priceRange': {'min': '.8', 'max': '.9'}}))
        profile = bot_rules.build_bot_rules('btc15_dual_live', settings={'entryRules': [rule]})
        entry = profile['sections'][0]['items']
        self.assertIn('3 minutes', entry[1]['detail'])
        self.assertIn('$7.50', entry[1]['detail'])
        self.assertIn('75¢–90¢', entry[1]['detail'])
        self.assertFalse(any(row['label'] == '5-minute rule' for row in entry))

    def test_scalp_rules_filter_candle_entries_but_empty_list_preserves_candles(self):
        entry = dict(decision='BUY NO', side='NO', prediction='DOWN', entry_price=Decimal('.8'), reason='candles down')
        args = dict(btc_price=992, target_price=1000, seconds_remaining=170, recent_prices=[995, 994, 993, 992])
        self.assertEqual('BUY NO', filter_scalp_entry(entry, [], **args)['decision'])
        self.assertEqual('BUY NO', filter_scalp_entry(entry, [custom_rule()], **args)['decision'])
        self.assertEqual('WAIT', filter_scalp_entry(entry, [custom_rule(maxMinutesLeft='2')], **args)['decision'])
        self.assertEqual('WAIT', filter_scalp_entry(entry, [custom_rule(enabled=False)], **args)['decision'])


class SavedRuleSettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        patches = patch.multiple(dashboard, ROOT=self.root, LOG_DIR=self.root / 'logs', BOT_PROCESSES={},
            BOT_TRADE_BUDGETS={}, BOT_DAILY_LIVE_LIMITS={}, BOT_ENTRY_PRICE_RANGES={}, BOT_ENTRY_RULES={})
        patches.start()
        self.addCleanup(patches.stop)

    def test_saving_while_running_changes_only_saved_preferences_and_keeps_the_active_snapshot(self):
        bot_id = 'btc15_dual_live'
        old = default_bot_preferences(bot_id)
        new = {**old, 'entryRules': [custom_rule()]}
        snapshot = bot_rules.build_bot_rules(bot_id, settings={'entryRules': old['entryRules'], 'tradeBudget': old['tradeBudget'], 'dailyLimit': old['dailyLiveOrderLimit']})
        runtime = dict(state='healthy', processAlive=True, blockers=[], settings={'entryRules': old['entryRules'],
            'ruleSnapshot': snapshot, 'tradeBudget': old['tradeBudget'], 'dailyLimit': old['dailyLiveOrderLimit']})
        with patch('dashboard.subprocess.Popen') as launch, patch('dashboard.os.killpg') as kill:
            result, status = dashboard.update_bot_settings(bot_id, new)
            self.assertEqual(200, status)
            launch.assert_not_called(); kill.assert_not_called()
        self.assertEqual(new, configured_bot_preferences(self.root, bot_id))
        self.assertEqual(old['entryRules'], default_bot_preferences(bot_id)['entryRules'])
        self.assertIsNone(saved_entry_rules(self.root, 'btc15_dual_paper'))
        with patch.object(dashboard, 'runtime_status', side_effect=lambda *args, **kwargs: copy.deepcopy(runtime)):
            shown = next(row for row in dashboard.bot_statuses() if row['id'] == bot_id)
        self.assertEqual(new, shown['settings'])
        self.assertEqual(snapshot['sections'], shown['rules']['sections'])

    def test_legacy_global_prices_migrate_into_each_rule_and_default_reset_removes_override(self):
        save_entry_price_range(self.root, 'btc15_dual_live', {'min': '.76', 'max': '.9'})
        preferences = configured_bot_preferences(self.root, 'btc15_dual_live')
        self.assertIsNone(preferences['entryPriceRange'])
        self.assertTrue(all(rule['priceRange'] == {'min': '0.7600', 'max': '0.9000'} for rule in preferences['entryRules']))
        self.assertEqual(200, dashboard.update_bot_settings('btc15_dual_live', default_bot_preferences('btc15_dual_live'))[1])
        self.assertEqual('0.8000', configured_bot_preferences(self.root, 'btc15_dual_live')['entryRules'][0]['priceRange']['min'])

    def test_saved_rules_reach_every_15m_runner_including_distances_below_ten_dollars(self):
        for bot_id in dashboard.BOTS:
            if bot_id == 'scalp_paper':
                continue
            dashboard.BOT_PROCESSES.clear()
            preferences = default_bot_preferences(bot_id)
            preferences['entryRules'] = [custom_rule(side='NO' if bot_id == 'btc15_paper' else 'BOTH')]
            process = Mock(pid=12345); process.poll.return_value = None
            with self.subTest(bot=bot_id), patch('dashboard.subprocess.Popen', return_value=process) as launch, patch('dashboard.time.sleep'), redirect_stdout(io.StringIO()):
                self.assertEqual(200, dashboard.update_bot_settings(bot_id, preferences)[1])
                loaded = configured_bot_preferences(self.root, bot_id)
                self.assertEqual(200, dashboard.start_bot(bot_id, expected_settings_fingerprint=preferences_fingerprint(loaded))[1])
                environment = launch.call_args.kwargs['env']
            self.assertEqual(preferences['entryRules'], json.loads(environment[RULES_ENV]))
            live = 'live' in bot_id
            decision = make_direction_paper_decision if 'direction' in bot_id else make_dual_live_decision if bot_id == 'btc15_dual_live' else make_late_momentum_decision
            with (
                patch.dict(os.environ, environment),
                patch.multiple(bot, BotTelemetry=DEFAULT, get_btc_price=DEFAULT,
                    get_current_market=DEFAULT, get_orderbook=DEFAULT, get_yes_quote=DEFAULT, get_seconds_remaining=DEFAULT,
                    log_market_data=DEFAULT, log_shadow_signal=DEFAULT, place_live_trade=DEFAULT, record_paper_trade=DEFAULT) as mocks,
                patch('bot.time.sleep', side_effect=[None] * 3 + [KeyboardInterrupt]), redirect_stdout(io.StringIO()),
            ):
                mocks['get_btc_price'].side_effect = ['992.4', '992.3', '992.2', '992.1']
                mocks['get_current_market'].return_value = {'ticker': 'RULE-TEST', 'floor_strike': '1000'}
                mocks['get_seconds_remaining'].return_value = 170
                mocks['get_yes_quote'].return_value = tuple(Decimal(x) for x in ('.18', '.2', '.78', '.8', '.02'))
                bot.main(live_enabled=live, live_bot_id=bot_id, paper_bot_id=bot_id, paper_sides=('NO',), decision_fn=decision)
                self.assertTrue(mocks['place_live_trade' if live else 'record_paper_trade'].called)
                self.assertEqual(preferences['entryRules'], mocks['BotTelemetry'].call_args.kwargs['settings']['entryRules'])

    def test_stale_settings_invalid_rules_and_disk_errors_cannot_launch_a_process(self):
        with patch('dashboard.subprocess.Popen') as launch:
            self.assertEqual(409, dashboard.start_bot('btc15_dual_live', expected_settings_fingerprint='stale')[1])
            invalid = {**default_bot_preferences('btc15_dual_live'), 'entryRules': [{'bad': True}]}
            self.assertEqual(400, dashboard.update_bot_settings('btc15_dual_live', invalid)[1])
            with patch.object(dashboard, 'save_bot_config', side_effect=OSError('disk unavailable')):
                self.assertEqual(500, dashboard.update_bot_settings('btc15_dual_live', default_bot_preferences('btc15_dual_live'))[1])
            launch.assert_not_called()

    def test_settings_post_routes_to_save_without_starting_or_stopping(self):
        preferences = default_bot_preferences('btc15_dual_live')
        body = json.dumps({'botId': 'btc15_dual_live', 'settings': preferences}).encode()
        handler = SimpleNamespace(path='/api/bots/settings', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
        with patch.object(dashboard, 'start_bot') as start, patch.object(dashboard, 'stop_bot') as stop, patch.object(dashboard, 'json_response') as respond:
            dashboard.DashboardHandler.do_POST(handler)
            self.assertEqual(200, respond.call_args.kwargs['status'])
            start.assert_not_called(); stop.assert_not_called()
        self.assertEqual(preferences, configured_bot_preferences(self.root, 'btc15_dual_live'))


if __name__ == '__main__':
    unittest.main()
