import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import DEFAULT, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bot
import dashboard
import direction_paper_bot
import paper_execution
from direction_strategy import make_direction_paper_decision
from entry_context import read_entry_contexts
from strategy import make_late_momentum_decision


class DirectionRuleTests(unittest.TestCase):
    def arguments(self, prices, seconds=300):
        return dict(btc_price=prices[-1], target_price=1000, seconds_remaining=seconds,
                    yes_ask="0.80", no_ask="0.80", spread="0.02", recent_prices=prices,
                    confirmation_count=3, enable_early_up=False)

    def test_both_sides_require_three_consecutive_strong_rule_moves(self):
        for side, prices in (("YES", [1060, 1062, 1064, 1066]), ("NO", [940, 938, 936, 934])):
            result = make_direction_paper_decision(**self.arguments(prices))
            self.assertEqual(f"BUY {side}", result["decision"])
            self.assertEqual("strong_5m_50_direction", result["strategy_name"])

    def test_chop_flat_latest_tick_and_short_history_are_blocked_without_changing_original_rule(self):
        for prices in ([1060, 1070, 1066, 1068], [940, 930, 934, 932],
                       [1060, 1062, 1064, 1064], [940, 938, 936, 936], [1060, 1062, 1064]):
            args = self.arguments(prices)
            self.assertTrue(make_late_momentum_decision(**args)["decision"].startswith("BUY"))
            self.assertEqual("WAIT", make_direction_paper_decision(**args)["decision"])
            self.assertEqual("WAIT", make_direction_paper_decision(**{**args, "seconds_remaining": 240})["decision"])

    def test_opposite_latest_movement_is_blocked_for_both_sides(self):
        for prices in ([1060, 1064, 1066, 1065], [940, 936, 934, 935]):
            self.assertEqual("WAIT", make_direction_paper_decision(**self.arguments(prices))["decision"])

    def test_late_rule_and_all_existing_strong_rule_limits_are_preserved(self):
        for side, prices in (("YES", [1010, 1015, 1013, 1014]), ("NO", [990, 985, 987, 986])):
            result = make_direction_paper_decision(**self.arguments(prices, seconds=240))
            self.assertEqual(f"BUY {side}", result["decision"])
            self.assertEqual("late_4m_10", result["strategy_name"])
        baseline = self.arguments([1060, 1062, 1064, 1066])
        for change in ({"seconds_remaining": 301}, {"seconds_remaining": 30}, {"spread": "0.04"},
                       {"confirmation_count": 2}, {"yes_ask": "0.93"}):
            self.assertEqual("WAIT", make_direction_paper_decision(**{**baseline, **change})["decision"])
        self.assertEqual("WAIT", make_direction_paper_decision(**self.arguments([1040, 1042, 1044, 1046]))["decision"])


class DirectionBotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "direction.csv"

    def run_bot(self, prices):
        side = "YES" if prices[-1] > 1000 else "NO"
        with (
            patch.multiple(bot, BotTelemetry=DEFAULT, LIVE_TRADING_ENABLED=True,
                           get_btc_price=DEFAULT, get_current_market=DEFAULT, get_seconds_remaining=DEFAULT,
                           get_orderbook=DEFAULT, log_market_data=DEFAULT, log_shadow_signal=DEFAULT,
                           place_live_trade=DEFAULT) as mocks,
            patch.object(direction_paper_bot, "DIRECTION_TRADE_FILE", str(self.path)),
            patch.object(direction_paper_bot, "RunLock") as lock,
            patch("bot.time.sleep", side_effect=[None] * (len(prices) - 1) + [KeyboardInterrupt]),
            redirect_stdout(io.StringIO()),
        ):
            mocks["get_btc_price"].side_effect = prices
            mocks["get_current_market"].return_value = {"ticker": "TEST", "floor_strike": "1000"}
            mocks["get_seconds_remaining"].return_value = 300
            mocks["get_orderbook"].return_value = {"orderbook_fp": {
                "yes_dollars": [["0.78" if side == "YES" else "0.20", 10]],
                "no_dollars": [["0.78" if side == "NO" else "0.20", 10]],
            }}
            direction_paper_bot.main()
            mocks["place_live_trade"].assert_not_called()
            lock.assert_called_once_with("btc15_direction_paper_bot")
            self.assertEqual("btc15_direction_paper", mocks["BotTelemetry"].call_args.args[0])
            self.assertEqual("data/direction_market_data.csv", mocks["log_market_data"].call_args.kwargs["data_file"])
        return paper_execution.read_trade_rows(self.path)

    def test_paper_only_separate_ledger_snapshots_and_restart_duplicate_guard(self):
        for side, prices in (("YES", [1060, 1062, 1064, 1066]), ("NO", [940, 938, 936, 934])):
            with self.subTest(side=side):
                self.path = self.root / f"{side}.csv"
                rows = self.run_bot(prices)
                self.assertEqual(1, len(rows))
                self.assertEqual(side, rows[0]["side"])
                self.assertEqual("125", rows[0]["contracts"])
                context = read_entry_contexts(self.path)[rows[0]["trade_id"]]
                self.assertEqual("MATCH", context["entry_direction_match"])
                self.assertEqual("RECORDED", context["entry_direction_basis"])
                self.assertEqual(str(prices[-1]), context["entry_btc_price"])
                self.assertEqual(str(prices[-1] - prices[-2]), context["entry_btc_change_usd"])
                self.assertEqual(1, len(self.run_bot(prices)))
                self.assertEqual(1, len(read_entry_contexts(self.path)))
                self.assertEqual(1, paper_execution.update_paper_trade_results(lambda _: side, trade_file=self.path))
                self.assertEqual("25.0000", paper_execution.read_trade_rows(self.path)[0]["profit_loss"])

    def test_dashboard_exposes_independent_paper_bot_and_direction_evidence(self):
        self.run_bot([940, 938, 936, 934])
        with patch.multiple(dashboard, DIRECTION_PAPER_FILE=self.path,
                            PAPER_FILE=self.root / "old.csv", DUAL_PAPER_FILE=self.root / "dual.csv",
                            LIVE_FILE=self.root / "live.csv", SCALP_FILE=self.root / "scalp.csv",
                            SHADOW_FILE=self.root / "shadow.csv", BOT_PROCESSES={}):
            payload = dashboard.build_payload()
        self.assertEqual(1, payload["directionPaper"]["total"])
        self.assertEqual(0, payload["dualPaper"]["total"])
        self.assertEqual("DOWN", payload["directionPaper"]["recent"][0]["entry_direction"])
        status = next(item for item in payload["bots"] if item["id"] == "btc15_direction_paper")
        self.assertEqual("paper", status["mode"])
        self.assertFalse(status["running"])
        self.assertEqual("false", dashboard.BOTS[status["id"]]["env"]["KALSHI_LIVE_TRADING"])


if __name__ == "__main__":
    unittest.main()
