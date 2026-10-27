import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bot
import dashboard
import live_execution
from trade_sizing import contracts_for_budget, parse_trade_budget


class TradeSizingTests(unittest.TestCase):
    def test_dollar_budgets_round_down_to_whole_contracts(self):
        cases = [
            ("1", "0.80", 1, "0.80"),
            ("100", "0.80", 125, "100"),
            ("100", "0.83", 120, "99.60"),
            ("250", "0.92", 271, "249.32"),
            ("0.75", "0.75", 1, "0.75"),
            ("1.01", "0.005", 202, "1.01"),
        ]
        for budget, price, expected, cost in cases:
            with self.subTest(budget=budget, price=price):
                quantity = contracts_for_budget(price, budget)
                self.assertEqual(expected, quantity)
                self.assertEqual(Decimal(cost), quantity * Decimal(price))
                self.assertLessEqual(quantity * Decimal(price), Decimal(budget))
                self.assertGreater((quantity + 1) * Decimal(price), Decimal(budget))

    def test_invalid_dollar_budgets_are_rejected_without_rounding_them(self):
        for value in ("", None, True, "NaN", "Infinity", "-Infinity", "0", "-1", "1.005", "1e100", {}, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_trade_budget(value)
        self.assertEqual(Decimal("100.00"), parse_trade_budget("100.000"))

    def test_price_and_funding_validation(self):
        for price in ("0", "-0.1", "1.01", "NaN", "Infinity", "not-a-price"):
            with self.subTest(price=price), self.assertRaises(ValueError):
                contracts_for_budget(price, "100")
        with self.assertRaisesRegex(ValueError, "at least one contract"):
            contracts_for_budget("0.80", "0.79")

    def test_bad_budget_cannot_start_the_bot_loop(self):
        with patch.object(bot, "get_btc_price") as prices, self.assertRaises(ValueError):
            bot.main(live_enabled=True, trade_budget="NaN")
        prices.assert_not_called()


class BudgetExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        patcher = patch.object(live_execution, "LIVE_TRADE_FILE", str(self.root / "live.csv"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_explicit_budget_is_enforced_and_logged_for_scaled_live_order(self):
        create = Mock(return_value={"order_id": "test", "fill_count": "120.00"})
        self.assertTrue(live_execution.place_live_trade(
            ticker="SCALED", side="YES", prediction="UP", entry_price="0.83",
            contracts=120, trade_budget="100", create_order_fn=create,
        ))
        self.assertEqual(120, create.call_args.kwargs["count"])
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("100.00", row["trade_budget"])
        self.assertEqual("99.6000", row["max_cost"])
        count = live_execution.update_live_trade_results(
            lambda ticker: "YES",
            get_fills_fn=lambda order_id, *, ticker: [{
                "order_id": order_id, "ticker": ticker, "count_fp": "120.00",
                "yes_price_dollars": "0.8300", "fee_cost": "1.2000",
            }],
        )
        self.assertEqual(1, count)
        settled = live_execution.read_live_trade_rows()[0]
        self.assertEqual("19.2000", settled["profit_loss"])

    def test_budget_ceiling_and_whole_contract_validation_prevent_submission(self):
        create = Mock()
        for contracts, budget in ((121, "100"), (125, "1"), (0, "100"), (-1, "100"), ("1.5", "100"), ("NaN", "100"), ("bad", "100")):
            with self.subTest(contracts=contracts, budget=budget), self.assertRaises(ValueError):
                live_execution.place_live_trade(
                    ticker="BAD", side="YES", prediction="UP", entry_price="0.83",
                    contracts=contracts, trade_budget=budget, create_order_fn=create,
                )
        create.assert_not_called()

    def test_live_quote_rounding_cannot_push_limit_cost_above_budget(self):
        for side in ("YES", "NO"):
            with self.subTest(side=side):
                price = live_execution.normalize_live_entry_price("0.819671")
                contracts = contracts_for_budget(price, "100")
                self.assertEqual(121, contracts)
                create = Mock(return_value={"order_id": f"order-{side}"})
                live_execution.place_live_trade(
                    ticker=f"ROUND-{side}", side=side, prediction="UP" if side == "YES" else "DOWN",
                    entry_price="0.819671", contracts=contracts, trade_budget="100", create_order_fn=create,
                )
                sent_price = create.call_args.kwargs["price"]
                entry_limit = sent_price if side == "YES" else Decimal("1") - sent_price
                self.assertLessEqual(entry_limit * contracts, Decimal("100"))
                self.assertEqual(Decimal("0.8197"), entry_limit)

    def test_dashboard_passes_validated_budget_to_each_15m_bot(self):
        for bot_id, config in dashboard.BOTS.items():
            if "budgetEnv" not in config:
                continue
            process = Mock(pid=12345)
            process.poll.return_value = None
            with (
                self.subTest(bot=bot_id),
                patch.multiple(dashboard, ROOT=self.root, LOG_DIR=self.root / "logs", BOT_PROCESSES={}, BOT_TRADE_BUDGETS={}),
                patch("dashboard.subprocess.Popen", return_value=process) as start,
                patch("dashboard.time.sleep"),
                redirect_stdout(io.StringIO()),
            ):
                response, status = dashboard.start_bot(bot_id, trade_budget="100")
                self.assertEqual(200, status)
                self.assertTrue(response["ok"])
                self.assertEqual("100.00", start.call_args.kwargs["env"][config["budgetEnv"]])
                bot_status = next(row for row in dashboard.bot_statuses() if row["id"] == bot_id)
                self.assertEqual("100.00", bot_status["tradeBudget"])
                self.assertTrue(bot_status["supportsTradeBudget"])

    def test_dashboard_rejects_invalid_budgets_before_launch(self):
        for budget in ("", "NaN", "0", "-100", "1.005", "not-money"):
            with self.subTest(budget=budget), patch("dashboard.subprocess.Popen") as start:
                result, status = dashboard.start_bot(live_execution.DUAL_LIVE_BOT_ID, trade_budget=budget)
                self.assertEqual(400, status)
                self.assertFalse(result["ok"])
                start.assert_not_called()

    def test_running_bot_cannot_silently_change_its_budget(self):
        running = Mock(pid=12345)
        running.poll.return_value = None
        with (
            patch.object(dashboard, "BOT_PROCESSES", {live_execution.DUAL_LIVE_BOT_ID: running}),
            patch.object(dashboard, "BOT_TRADE_BUDGETS", {live_execution.DUAL_LIVE_BOT_ID: Decimal("1.00")}),
            patch("dashboard.subprocess.Popen") as start,
        ):
            result, status = dashboard.start_bot(live_execution.DUAL_LIVE_BOT_ID, trade_budget="100")
        self.assertEqual(409, status)
        self.assertIn("Stop", result["message"])
        start.assert_not_called()

    def test_scalp_budget_is_not_changed_by_this_setting(self):
        with patch("dashboard.subprocess.Popen") as start:
            result, status = dashboard.start_bot("scalp_paper", trade_budget="100")
        self.assertEqual(400, status)
        self.assertFalse(result["ok"])
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
