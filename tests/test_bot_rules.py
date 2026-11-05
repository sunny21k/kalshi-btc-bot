import copy
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import bot_rules
import bot_telemetry
import dashboard
import strategy


def detail(profile, label):
    return next(item['detail'] for section in profile['sections'] for item in section['items'] if item['label'] == label)


class BotRuleTests(unittest.TestCase):
    def test_every_registered_bot_has_its_own_profile_and_correct_trade_mode(self):
        for bot_id, config in dashboard.BOTS.items():
            with self.subTest(bot_id=bot_id):
                profile = bot_rules.build_bot_rules(bot_id)
                self.assertEqual(bot_id, profile['botId'])
                self.assertEqual(config['mode'], profile['mode'])
                self.assertEqual(4, len(profile['sections']))
                self.assertTrue(profile['fingerprint'])

    def test_live_80_cent_band_is_not_attributed_to_paper_or_original_live(self):
        updated = bot_rules.build_bot_rules('btc15_dual_live')
        self.assertIn('80¢–92¢', detail(updated, '5-minute rule'))
        self.assertIn('75¢–85¢', detail(updated, '4-minute rule'))
        for bot_id in ('btc15_paper', 'btc15_dual_paper', 'btc15_direction_paper', 'btc15_live'):
            self.assertIn('75¢–92¢', detail(bot_rules.build_bot_rules(bot_id), '5-minute rule'))
        self.assertIn('NO only', detail(bot_rules.build_bot_rules('btc15_paper'), 'Bought side'))
        self.assertIn('9 minutes', detail(bot_rules.build_bot_rules('btc15_live'), 'Early YES entry'))
        direction = bot_rules.build_bot_rules('btc15_direction_paper')
        self.assertIn('strictly falling for NO', detail(direction, 'Extra direction check'))
        self.assertNotIn('Extra direction check', [item['label'] for section in updated['sections'] for item in section['items']])

    def test_descriptions_follow_strategy_constants_and_selected_budget_and_cap(self):
        with patch.multiple(strategy, MAX_STRONG_ENTRY_SECONDS=Decimal('270'), MIN_STRONG_BTC_PRICE_DIFFERENCE=Decimal('60'), MIN_DUAL_LIVE_STRONG_ENTRY_PRICE=Decimal('0.82')):
            profile = bot_rules.build_bot_rules('btc15_dual_live', settings={'tradeBudget': '125.50', 'dailyLimit': 0})
        self.assertIn('4.5 minutes', detail(profile, '5-minute rule'))
        self.assertIn('$60.00', detail(profile, '5-minute rule'))
        self.assertIn('82¢–92¢', detail(profile, '5-minute rule'))
        self.assertIn('$125.50', detail(profile, 'Entry budget'))
        self.assertIn('Disabled', detail(profile, 'Daily order cap'))

    def test_scalp_details_use_supplied_runtime_settings_and_total_position_thresholds(self):
        config = dict(bot_rules.scalp_settings(), ALLOWED_SIDES=['NO'], CONTRACTS=4,
                      MIN_SECONDS_REMAINING='120', TRAILING_ACTIVATION='0.15',
                      TRAILING_GIVEBACK='0.05', STOP_LOSS='0.10')
        profile = bot_rules.build_bot_rules('scalp_paper', settings={'scalp': config})
        self.assertEqual('NO', detail(profile, 'Allowed sides'))
        self.assertIn('4 whole contracts', detail(profile, 'Contracts'))
        self.assertIn('120 seconds', detail(profile, 'Entry cutoff'))
        self.assertIn('−$0.10', detail(profile, 'Stop loss'))
        self.assertIn('$0.15', detail(profile, 'Trailing giveback'))
        self.assertIn('entire position', detail(profile, 'Trailing giveback'))
        self.assertIn('not restored', detail(profile, 'Stop or restart'))

    def test_running_snapshot_is_preserved_when_current_code_changes(self):
        snapshot = bot_rules.build_bot_rules('btc15_dual_live', settings={'tradeBudget': '100', 'dailyLimit': 30})
        before = copy.deepcopy(snapshot)
        runtime = {'processAlive': True, 'settings': {'ruleSnapshot': snapshot}}
        with patch.object(strategy, 'MIN_DUAL_LIVE_STRONG_ENTRY_PRICE', Decimal('0.85')):
            reported = bot_rules.reported_rules('btc15_dual_live', runtime, settings={'tradeBudget': '100', 'dailyLimit': 30})
        self.assertEqual('running', reported['source'])
        self.assertFalse(reported['matchesCurrent'])
        self.assertIn('80¢–92¢', detail(reported, '5-minute rule'))
        self.assertEqual(before, snapshot)

    def test_unreported_and_stopped_processes_show_current_rules_without_claiming_a_snapshot(self):
        current = bot_rules.reported_rules('btc15_dual_live', {'processAlive': True}, settings={})
        self.assertEqual('current', current['source'])
        self.assertTrue(current['runningWithoutSnapshot'])
        wrong = bot_rules.build_bot_rules('btc15_paper')
        current = bot_rules.reported_rules('btc15_dual_live', {'processAlive': True, 'settings': {'ruleSnapshot': wrong}}, settings={})
        self.assertEqual('btc15_dual_live', current['botId'])
        self.assertEqual('current', current['source'])

    def test_optional_snapshot_errors_cannot_prevent_telemetry_or_a_bot_from_starting(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bot_telemetry, 'STATUS_DIR', Path(directory)):
            reporter = bot_telemetry.BotTelemetry('btc15_dual_live', settings={'tradeBudget': '100', 'dailyLimit': 0})
            self.assertIn('80¢–92¢', detail(reporter.data['settings']['ruleSnapshot'], '5-minute rule'))
            with patch.object(bot_telemetry, 'build_bot_rules', side_effect=RuntimeError('optional description unavailable')):
                reporter = bot_telemetry.BotTelemetry('btc15_paper')
                reporter.price('90000')
            self.assertEqual('90000', reporter.data['price']['value'])
            self.assertTrue(reporter.path.exists())

    def test_dashboard_rules_are_read_only_and_cover_all_six_bots(self):
        def stopped(*args, **kwargs):
            return {'state': 'stopped', 'processAlive': False, 'settings': {}, 'blockers': []}
        with patch.object(dashboard, 'BOT_PROCESSES', {}), patch.object(dashboard, 'runtime_status', side_effect=stopped), patch('kalshi_api.create_order') as order, patch('kalshi_api.get_market') as market:
            statuses = dashboard.bot_statuses()
        self.assertEqual(6, len(statuses))
        self.assertTrue(all(status['id'] == status['rules']['botId'] for status in statuses))
        order.assert_not_called()
        market.assert_not_called()


if __name__ == '__main__':
    unittest.main()
