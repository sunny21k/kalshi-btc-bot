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
import dual_paper_bot
import paper_execution
import performance
from strategy import make_late_momentum_decision


class DualPaperBotTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.old_path = self.root / "paper_trades.csv"
        self.path = self.root / "dual_paper_trades.csv"
        patcher = patch.object(paper_execution, "TRADE_FILE", str(self.old_path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_rows(self):
        with self.path.open(newline="") as file:
            return list(csv.DictReader(file))

    def record(self, ticker, side="NO", *, path=None):
        return paper_execution.record_paper_trade(
            ticker=ticker,
            side=side,
            prediction="UP" if side == "YES" else "DOWN",
            entry_price="0.80",
            model_probability="0.80",
            edge="0",
            strategy_name="late_4m_10",
            trade_file=path,
        )

    def run_bot(self, prices, seconds, *, ticker="KXBTC15M-TEST"):
        side = "YES" if prices[-1] > 82323 else "NO"
        with (
            patch.multiple(
                bot,
                LIVE_TRADING_ENABLED=True,
                get_btc_price=DEFAULT,
                get_current_market=DEFAULT,
                get_seconds_remaining=DEFAULT,
                get_orderbook=DEFAULT,
                log_market_data=DEFAULT,
                log_shadow_signal=DEFAULT,
                place_live_trade=DEFAULT,
            ) as mocks,
            patch.object(dual_paper_bot, "DUAL_TRADE_FILE", str(self.path)),
            patch.object(dual_paper_bot, "RunLock") as lock,
            patch("bot.time.sleep", side_effect=[None] * (len(prices) - 1) + [KeyboardInterrupt]),
            redirect_stdout(io.StringIO()),
        ):
            mocks["get_btc_price"].side_effect = prices
            mocks["get_current_market"].return_value = {
                "ticker": ticker,
                "floor_strike": "82323",
            }
            mocks["get_seconds_remaining"].return_value = seconds
            mocks["get_orderbook"].return_value = {
                "orderbook_fp": {
                    "yes_dollars": [["0.78" if side == "YES" else "0.20", 10]],
                    "no_dollars": [["0.78" if side == "NO" else "0.20", 10]],
                },
            }

            dual_paper_bot.main()

            lock.assert_called_once_with("btc15_dual_paper_bot")
            mocks["place_live_trade"].assert_not_called()
            self.assertTrue(all(
                call.kwargs["live_enabled"] is False
                for call in mocks["log_shadow_signal"].call_args_list
            ))
            return mocks["log_shadow_signal"].call_args.kwargs["trade_signal"]

    def test_both_sides_use_only_the_requested_rules_and_separate_ledger(self):
        self.record("KXBTC15M-YES-LATE")
        original = self.old_path.read_bytes()
        scenarios = [
            ("YES-LATE", "YES", [82340, 82341, 82342], 180, "late_4m_10"),
            ("NO-LATE", "NO", [82305, 82304, 82303], 240, "late_4m_10"),
            ("YES-STRONG", "YES", [82400, 82401, 82402], 270, "strong_5m_50"),
            ("NO-STRONG", "NO", [82272, 82271, 82270], 300, "strong_5m_50"),
        ]
        for name, side, prices, seconds, strategy in scenarios:
            with self.subTest(name=name):
                ticker = f"KXBTC15M-{name}"
                signal = self.run_bot(prices, seconds, ticker=ticker)
                self.assertEqual(f"BUY {side}", signal["decision"])
                row = next(row for row in self.read_rows() if row["ticker"] == ticker)
                self.assertEqual(side, row["side"])
                self.assertEqual(strategy, row["strategy_name"])
                self.assertEqual("125", row["contracts"])
                self.assertEqual("100.0000", row["cost"])
                self.assertEqual("", row["actual_result"])
        self.assertEqual(4, len(self.read_rows()))
        self.assertEqual(original, self.old_path.read_bytes())

    def test_repeated_polls_and_restart_cannot_trade_same_market_twice(self):
        self.run_bot([82340, 82341, 82342, 82343], 180)
        self.run_bot([82305, 82304, 82303, 82302], 180)
        rows = self.read_rows()
        self.assertEqual(1, len(rows))
        self.assertEqual("YES", rows[0]["side"])
        self.assertFalse(self.old_path.exists())

    def test_disabled_early_rule_and_insufficient_distances_do_not_trade(self):
        scenarios = [
            ([82400, 82401, 82402], 500),
            ([82400, 82401, 82402], 301),
            ([82340, 82341, 82342], 270),
            ([82328, 82329, 82330], 180),
            ([82305, 82304, 82303], 30),
        ]
        for prices, seconds in scenarios:
            with self.subTest(prices=prices, seconds=seconds):
                signal = self.run_bot(prices, seconds)
                self.assertEqual("WAIT", signal["decision"])
                self.assertEqual([], self.read_rows())

    def test_duplicate_guards_are_independent_between_paper_ledgers(self):
        self.assertTrue(self.record("SAME", path=self.path))
        self.assertTrue(self.record("SAME"))
        self.assertFalse(self.record("SAME", side="YES", path=self.path))
        self.assertFalse(self.record("SAME", side="YES"))

    def test_settlement_updates_new_ledger_only_and_can_retry_pending_markets(self):
        self.record("OLD")
        original = self.old_path.read_bytes()
        for ticker, side in (("YES-WIN", "YES"), ("NO-WIN", "NO"), ("LOSS", "NO"), ("PENDING", "YES")):
            self.record(ticker, side, path=self.path)
        results = {"YES-WIN": "YES", "NO-WIN": "NO", "LOSS": "YES"}
        count = paper_execution.update_paper_trade_results(results.get, trade_file=self.path)
        self.assertEqual(3, count)
        rows = {row["ticker"]: row for row in self.read_rows()}
        self.assertEqual("0.2000", rows["YES-WIN"]["profit_loss"])
        self.assertEqual("0.2000", rows["NO-WIN"]["profit_loss"])
        self.assertEqual("-0.8000", rows["LOSS"]["profit_loss"])
        self.assertEqual("", rows["PENDING"]["profit_loss"])
        self.assertEqual(0, paper_execution.update_paper_trade_results(results.get, trade_file=self.path))
        results["PENDING"] = "YES"
        self.assertEqual(1, paper_execution.update_paper_trade_results(results.get, trade_file=self.path))
        self.assertEqual(original, self.old_path.read_bytes())

    def test_dashboard_has_independent_bot_and_empty_or_populated_stats(self):
        self.record("OLD")
        with patch.multiple(
            dashboard,
            PAPER_FILE=self.old_path,
            DUAL_PAPER_FILE=self.path,
            LIVE_FILE=self.root / "live.csv",
            SCALP_FILE=self.root / "scalp.csv",
            SHADOW_FILE=self.root / "shadow.csv",
            BOT_PROCESSES={},
        ):
            payload = dashboard.build_payload()
            self.assertEqual(0, payload["dualPaper"]["total"])
            self.assertEqual([], payload["dualPaper"]["recent"])
            self.record("NEW", "YES", path=self.path)
            payload = dashboard.build_payload()
        self.assertEqual(1, payload["paper"]["total"])
        self.assertEqual(1, payload["dualPaper"]["yes"]["total"])
        self.assertEqual("NEW", payload["dualPaper"]["recent"][0]["ticker"])
        status = next(bot for bot in payload["bots"] if bot["id"] == "btc15_dual_paper")
        self.assertFalse(status["running"])
        self.assertEqual("paper", status["mode"])
        self.assertEqual("false", dashboard.BOTS[status["id"]]["env"]["KALSHI_LIVE_TRADING"])

    def test_performance_report_reads_only_the_new_ledger(self):
        self.record("NEW", path=self.path)
        paper_execution.update_paper_trade_results(lambda ticker: "NO", trade_file=self.path)
        output = io.StringIO()
        with patch.object(performance, "DUAL_TRADE_FILE", str(self.path)), redirect_stdout(output):
            performance.print_dual_paper_trade_performance()
        self.assertIn("YES/NO PAPER TRADING PERFORMANCE", output.getvalue())
        self.assertIn("Total YES/NO Paper Trades: 1", output.getvalue())
        self.assertIn("Total Profit/Loss: $0.2000", output.getvalue())


class DualPaperRuleTests(unittest.TestCase):
    def decide(self, distance, seconds, **kwargs):
        return make_late_momentum_decision(
            btc_price=1000 + distance,
            target_price=1000,
            seconds_remaining=seconds,
            yes_ask="0.80",
            no_ask="0.80",
            confirmation_count=3,
            enable_early_up=False,
            **kwargs,
        )

    def test_exact_time_and_distance_boundaries_for_both_sides(self):
        for sign, side in ((1, "YES"), (-1, "NO")):
            for distance, seconds, strategy in ((10, 240, "late_4m_10"), (50, 300, "strong_5m_50")):
                with self.subTest(side=side, seconds=seconds):
                    result = self.decide(sign * distance, seconds)
                    self.assertEqual(f"BUY {side}", result["decision"])
                    self.assertEqual(strategy, result["strategy_name"])
                    self.assertEqual("WAIT", self.decide(sign * (distance - 1), seconds)["decision"])
                    self.assertEqual("WAIT", self.decide(sign * distance, seconds + 1)["decision"])

    def test_new_mode_retains_spread_and_confirmation_checks(self):
        self.assertEqual("WAIT", self.decide(60, 270, spread="0.04")["decision"])
        with patch("strategy.MIN_CONFIRMATION_POLLS", 4):
            self.assertEqual("WAIT", self.decide(-60, 270)["decision"])


if __name__ == "__main__":
    unittest.main()
