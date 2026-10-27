import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
from functools import partial
from pathlib import Path
from unittest.mock import DEFAULT, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bot
import dashboard
import dual_live_bot
import kalshi_api
import live_execution
import performance


class DualLiveBotTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.path = self.root / "live_trades.csv"
        for target, name, value in (
            (live_execution, "LIVE_TRADE_FILE", str(self.path)),
            (live_execution, "MAX_DAILY_LIVE_LOSS", Decimal("10")),
            (performance, "LIVE_TRADE_FILE", str(self.path)),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def row(self, **overrides):
        row = {field: "" for field in live_execution.FIELDNAMES}
        row.update({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_id": "live-test",
            "ticker": "KXBTC15M-TEST",
            "bot_id": live_execution.DUAL_LIVE_BOT_ID,
            "side": "YES",
            "prediction": "UP",
            "contracts": "1",
            "submitted_count": "1",
            "entry_price": "0.8000",
            "max_cost": "0.8000",
            "filled_count": "1.00",
            "fill_cost": "0.8000",
            "fees_paid": "0.0200",
            "order_id": "order-test",
            "status": "executed",
        })
        row.update(overrides)
        return row

    def run_bot(self, prices, seconds, *, ticker="KXBTC15M-TEST", budget="1.00"):
        side = "YES" if prices[-1] > 82323 else "NO"
        create = Mock(return_value={"order_id": f"order-{ticker}", "fill_count": "1.00"})
        with (
            patch.multiple(
                bot,
                LIVE_TRADING_ENABLED=False,
                get_btc_price=DEFAULT,
                get_current_market=DEFAULT,
                get_seconds_remaining=DEFAULT,
                get_orderbook=DEFAULT,
                log_market_data=DEFAULT,
                log_shadow_signal=DEFAULT,
                record_paper_trade=DEFAULT,
                contracts_for_budget=DEFAULT,
            ) as mocks,
            patch.object(bot, "place_live_trade", wraps=partial(live_execution.place_live_trade, create_order_fn=create)),
            patch.object(dual_live_bot, "RunLock") as lock,
            patch.dict("os.environ", {"KALSHI_LIVE_TRADING": "true", "KALSHI_LIVE_TRADE_BUDGET": budget}),
            patch("bot.time.sleep", side_effect=[None] * (len(prices) - 1) + [KeyboardInterrupt]),
            redirect_stdout(io.StringIO()),
        ):
            mocks["get_btc_price"].side_effect = prices
            mocks["get_current_market"].return_value = {"ticker": ticker, "floor_strike": "82323"}
            mocks["get_seconds_remaining"].return_value = seconds
            mocks["get_orderbook"].return_value = {
                "orderbook_fp": {
                    "yes_dollars": [["0.78" if side == "YES" else "0.20", 10]],
                    "no_dollars": [["0.78" if side == "NO" else "0.20", 10]],
                },
            }
            dual_live_bot.main()
            lock.assert_called_once_with("btc15_live_bot")
            mocks["record_paper_trade"].assert_not_called()
            mocks["contracts_for_budget"].assert_not_called()
            self.assertTrue(all(
                call.kwargs["live_enabled"] is True
                for call in mocks["log_shadow_signal"].call_args_list
            ))
            return create, mocks["log_shadow_signal"].call_args.kwargs["trade_signal"]

    def test_same_four_entry_scenarios_as_paper_but_one_real_contract(self):
        scenarios = [
            ("YES-LATE", "YES", [82340, 82341, 82342], 180, "late_4m_10"),
            ("NO-LATE", "NO", [82305, 82304, 82303], 240, "late_4m_10"),
            ("YES-STRONG", "YES", [82400, 82401, 82402], 270, "strong_5m_50"),
            ("NO-STRONG", "NO", [82272, 82271, 82270], 300, "strong_5m_50"),
        ]
        for name, side, prices, seconds, strategy in scenarios:
            with self.subTest(name=name):
                ticker = f"KXBTC15M-{name}"
                create, signal = self.run_bot(prices, seconds, ticker=ticker)
                self.assertEqual(f"BUY {side}", signal["decision"])
                self.assertEqual(strategy, signal["strategy_name"])
                create.assert_called_once()
                self.assertEqual(1, create.call_args.kwargs["count"])
                self.assertEqual("immediate_or_cancel", create.call_args.kwargs["time_in_force"])
                self.assertEqual("bid" if side == "YES" else "ask", create.call_args.kwargs["side"])
                self.assertEqual(Decimal("0.80" if side == "YES" else "0.20"), create.call_args.kwargs["price"])
        rows = live_execution.read_live_trade_rows()
        self.assertEqual(4, len(rows))
        self.assertTrue(all(row["contracts"] == "1" and row["max_cost"] == "0.8000" for row in rows))
        self.assertTrue(all(row["bot_id"] == live_execution.DUAL_LIVE_BOT_ID for row in rows))

    def test_early_rule_and_undersized_distance_stay_disabled(self):
        for prices, seconds in (([82400, 82401, 82402], 500), ([82400, 82401, 82402], 301), ([82340, 82341, 82342], 270), ([82305, 82304, 82303], 30)):
            with self.subTest(seconds=seconds):
                create, signal = self.run_bot(prices, seconds)
                create.assert_not_called()
                self.assertEqual("WAIT", signal["decision"])

    def test_chosen_100_dollar_budget_scales_both_yes_and_no_entries(self):
        for side, prices in (("YES", [82340, 82341, 82342]), ("NO", [82305, 82304, 82303])):
            with self.subTest(side=side):
                create, _ = self.run_bot(prices, 180, ticker=f"SCALED-{side}", budget="100")
                create.assert_called_once()
                self.assertEqual(125, create.call_args.kwargs["count"])
        rows = live_execution.read_live_trade_rows()
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row["trade_budget"] == "100.00" for row in rows))
        self.assertTrue(all(row["submitted_count"] == "125" for row in rows))
        self.assertTrue(all(row["max_cost"] == "100.0000" for row in rows))

    def test_restart_and_switching_live_bots_cannot_duplicate_a_market(self):
        first, _ = self.run_bot([82340, 82341, 82342, 82343], 180)
        second, _ = self.run_bot([82305, 82304, 82303, 82302], 180)
        other_create = Mock()
        self.assertFalse(live_execution.place_live_trade(
            ticker="KXBTC15M-TEST", side="NO", prediction="DOWN", entry_price="0.80",
            bot_id=live_execution.LEGACY_LIVE_BOT_ID, create_order_fn=other_create,
        ))
        first.assert_called_once()
        second.assert_not_called()
        other_create.assert_not_called()
        self.assertEqual(1, len(live_execution.read_live_trade_rows()))

    def test_explicit_live_opt_in_is_required_before_lock_or_runner(self):
        for enabled in ("", "false"):
            with (
                self.subTest(enabled=enabled),
                patch.dict("os.environ", {"KALSHI_LIVE_TRADING": enabled}),
                patch.object(dual_live_bot, "run_bot") as runner,
                patch.object(dual_live_bot, "RunLock") as lock,
                self.assertRaisesRegex(SystemExit, "Live trading disabled"),
            ):
                dual_live_bot.main()
            runner.assert_not_called()
            lock.assert_not_called()

    def test_shared_live_process_lock_failure_cannot_start_runner(self):
        with (
            patch.dict("os.environ", {"KALSHI_LIVE_TRADING": "true"}),
            patch.object(dual_live_bot, "RunLock") as lock,
            patch.object(dual_live_bot, "run_bot") as runner,
        ):
            lock.return_value.__enter__.side_effect = RuntimeError("already locked")
            with self.assertRaisesRegex(SystemExit, "already locked"):
                dual_live_bot.main()
            runner.assert_not_called()

    def test_shared_daily_cap_includes_both_bots_and_failed_attempts(self):
        live_execution.write_live_trade_rows([
            self.row(
                ticker=f"OLD-{index}", trade_id=f"live-{index}",
                bot_id=live_execution.DUAL_LIVE_BOT_ID if index % 2 else live_execution.LEGACY_LIVE_BOT_ID,
                error="uncertain submission" if index == 29 else "",
            ) for index in range(30)
        ])
        create = Mock()
        with self.assertRaisesRegex(RuntimeError, "Daily live trade limit reached"):
            live_execution.place_live_trade(
                ticker="NEW", side="YES", prediction="UP", entry_price="0.80",
                bot_id=live_execution.DUAL_LIVE_BOT_ID, create_order_fn=create,
            )
        create.assert_not_called()

    def test_legacy_losses_and_size_limits_block_new_bot_orders(self):
        live_execution.write_live_trade_rows([self.row(
            bot_id=live_execution.LEGACY_LIVE_BOT_ID, ticker="LOSS", profit_loss="-10.0000",
        )])
        create = Mock()
        with self.assertRaisesRegex(RuntimeError, "Daily live loss limit reached"):
            live_execution.place_live_trade(
                ticker="NEW", side="YES", prediction="UP", entry_price="0.80",
                bot_id=live_execution.DUAL_LIVE_BOT_ID, create_order_fn=create,
            )
        live_execution.write_live_trade_rows([])
        with self.assertRaisesRegex(ValueError, "exceeds.*budget"):
            live_execution.place_live_trade(
                ticker="NEW", side="YES", prediction="UP", entry_price="0.80", contracts=125,
                bot_id=live_execution.DUAL_LIVE_BOT_ID, create_order_fn=create,
            )
        create.assert_not_called()

    def test_submission_is_reserved_before_network_and_unknown_is_not_retried(self):
        def interrupted_submission(ticker, **kwargs):
            pending = live_execution.read_live_trade_rows()
            self.assertEqual(1, len(pending))
            self.assertEqual("SUBMITTING", pending[0]["status"])
            self.assertEqual(kwargs["client_order_id"], pending[0]["client_order_id"])
            raise TimeoutError("response missing")

        with self.assertRaises(TimeoutError):
            live_execution.place_live_trade(
                ticker="NEW", side="YES", prediction="UP", entry_price="0.80",
                bot_id=live_execution.DUAL_LIVE_BOT_ID, create_order_fn=interrupted_submission,
            )
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("SUBMISSION_UNKNOWN", row["status"])
        self.assertEqual("UNKNOWN", live_execution.live_fill_status(row))
        self.assertEqual(1, live_execution.live_trade_count_today())
        retry = Mock()
        self.assertFalse(live_execution.place_live_trade(
            ticker="NEW", side="YES", prediction="UP", entry_price="0.80", create_order_fn=retry,
        ))
        retry.assert_not_called()

    def test_tagged_orders_settle_using_fills_and_fees_and_report_separately(self):
        self.run_bot([82340, 82341, 82342], 180)
        count = live_execution.update_live_trade_results(
            lambda ticker: "YES",
            get_fills_fn=lambda order_id, *, ticker: [{
                "order_id": order_id, "ticker": ticker, "count_fp": "1.00",
                "yes_price_dollars": "0.7900", "no_price_dollars": "0.2100", "fee_cost": "0.0200",
            }],
        )
        self.assertEqual(1, count)
        rows = live_execution.read_live_trade_rows()
        rows.append(self.row(bot_id="", ticker="OLD", profit_loss="0.1800", actual_result="YES"))
        live_execution.write_live_trade_rows(rows)
        self.assertEqual("0.1900", rows[0]["profit_loss"])
        self.assertEqual(live_execution.DUAL_LIVE_BOT_ID, rows[0]["bot_id"])
        legacy = dashboard.live_trade_stats(rows, bot_id=live_execution.LEGACY_LIVE_BOT_ID)
        dual = dashboard.live_trade_stats(rows, bot_id=live_execution.DUAL_LIVE_BOT_ID)
        self.assertEqual(1, legacy["total"])
        self.assertEqual(1, dual["total"])
        self.assertEqual("0.1900", dual["profitLoss"])
        self.assertEqual("0.7900", dual["totalTraded"])
        output = io.StringIO()
        with redirect_stdout(output):
            performance.print_dual_live_trade_performance()
        self.assertIn("Total YES/NO Live Trades: 1", output.getvalue())
        self.assertIn("Total Profit/Loss: $0.1900", output.getvalue())

    def test_legacy_schema_migration_preserves_backup_and_owner(self):
        fields = [field for field in live_execution.FIELDNAMES if field != "bot_id"]
        with self.path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerow({key: value for key, value in self.row().items() if key != "bot_id"})
        original = self.path.read_bytes()
        rows = live_execution.read_live_trade_rows()
        self.assertEqual(live_execution.LEGACY_LIVE_BOT_ID, rows[0]["bot_id"])
        backup = next(self.root.glob("live_trades.csv.backup-*"))
        self.assertEqual(original, backup.read_bytes())

    def test_dashboard_blocks_other_live_runner_without_launching_process(self):
        running = Mock()
        running.poll.return_value = None
        with (
            patch.object(dashboard, "BOT_PROCESSES", {"btc15_live": running}),
            patch.object(dashboard, "LOG_DIR", self.root),
            patch("dashboard.subprocess.Popen") as start,
            redirect_stdout(io.StringIO()),
        ):
            result, status = dashboard.start_bot(live_execution.DUAL_LIVE_BOT_ID)
        self.assertEqual(409, status)
        self.assertIn("Stop", result["message"])
        start.assert_not_called()

    def test_order_adapter_uses_v2_fixed_point_fields_and_ioc_with_mocked_transport(self):
        with patch("kalshi_api.request", return_value={"order_id": "mocked"}) as request:
            kalshi_api.create_order(
                "TEST", side="ask", count=1, price=Decimal("0.20"), client_order_id="test-client",
            )
        self.assertEqual(("POST", "/trade-api/v2/portfolio/events/orders"), request.call_args.args)
        payload = request.call_args.kwargs["json"]
        self.assertEqual("1", payload["count"])
        self.assertEqual("0.2000", payload["price"])
        self.assertEqual("immediate_or_cancel", payload["time_in_force"])

    def test_dashboard_payload_isolates_new_bot_from_legacy_history(self):
        live_execution.write_live_trade_rows([
            self.row(ticker="NEW", actual_result="YES", profit_loss="0.1800"),
            self.row(ticker="OLD", bot_id="", actual_result="NO", profit_loss="-0.8200"),
        ])
        with patch.multiple(
            dashboard,
            LIVE_FILE=self.path,
            PAPER_FILE=self.root / "paper.csv",
            DUAL_PAPER_FILE=self.root / "dual_paper.csv",
            SCALP_FILE=self.root / "scalp.csv",
            SHADOW_FILE=self.root / "shadow.csv",
            BOT_PROCESSES={},
        ):
            payload = dashboard.build_payload()
        self.assertEqual("0.1800", payload["dualLive"]["profitLoss"])
        self.assertEqual("-0.8200", payload["live"]["profitLoss"])
        self.assertEqual("NEW", payload["dualLive"]["recent"][0]["ticker"])
        self.assertEqual("OLD", payload["live"]["recent"][0]["ticker"])
        status = next(row for row in payload["bots"] if row["id"] == live_execution.DUAL_LIVE_BOT_ID)
        self.assertFalse(status["running"])
        self.assertEqual("live", status["mode"])

    def test_dashboard_start_uses_live_entry_point_with_mocked_process_only(self):
        process = Mock(pid=12345)
        process.poll.return_value = None
        log_dir = self.root / "bot_logs"
        with (
            patch.object(dashboard, "ROOT", self.root),
            patch.object(dashboard, "BOT_PROCESSES", {}),
            patch.object(dashboard, "LOG_DIR", log_dir),
            patch("dashboard.subprocess.Popen", return_value=process) as start,
            patch("dashboard.time.sleep"),
            redirect_stdout(io.StringIO()),
        ):
            result, status = dashboard.start_bot(live_execution.DUAL_LIVE_BOT_ID)
        self.assertEqual(200, status)
        self.assertTrue(result["ok"])
        self.assertEqual("dual_live_bot.py", Path(start.call_args.args[0][1]).name)
        self.assertEqual("true", start.call_args.kwargs["env"]["KALSHI_LIVE_TRADING"])
        self.assertTrue(start.call_args.kwargs["stdout"].closed)


if __name__ == "__main__":
    unittest.main()
