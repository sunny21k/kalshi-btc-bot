import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import dashboard
import live_execution


class DailyLiveLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        patcher = patch.multiple(
            live_execution,
            LIVE_TRADE_FILE=str(Path(self.tmpdir.name) / "live.csv"),
            MAX_LIVE_TRADES_PER_DAY=30,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_parser_accepts_whole_numbers_and_explicit_zero(self):
        for value, expected in ((0, 0), ("0", 0), (1, 1), ("60", 60), (" 96 ", 96)):
            with self.subTest(value=value):
                self.assertEqual(expected, live_execution.parse_daily_live_trade_limit(value))

    def test_bad_configuration_cannot_silently_disable_the_cap(self):
        for value in (None, "", True, False, -1, "-1", "1.5", 30.0, "NaN", "Infinity", "unlimited", "1e2", {}, [], "３０"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                live_execution.parse_daily_live_trade_limit(value)

    def test_environment_configuration_is_loaded_and_invalid_values_fail_closed(self):
        for value, expected in (("60", "60"), ("0", "0"), ("-1", None), ("bad", None)):
            with self.subTest(value=value):
                env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "KALSHI_MAX_LIVE_TRADES_PER_DAY": value}
                result = subprocess.run(
                    [sys.executable, "-c", "from live_execution import MAX_LIVE_TRADES_PER_DAY; print(MAX_LIVE_TRADES_PER_DAY)"],
                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=10,
                )
                if expected is None:
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("Daily live order limit", result.stderr)
                else:
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(expected, result.stdout.strip())

    def test_custom_cap_blocks_at_the_boundary(self):
        with (
            patch.object(live_execution, "MAX_LIVE_TRADES_PER_DAY", 5),
            patch.object(live_execution, "live_trade_count_today", return_value=4) as count,
            patch.object(live_execution, "realized_live_profit_loss_today", return_value=Decimal("0")),
        ):
            live_execution.validate_live_risk_limits()
            for attempts in (5, 6):
                count.return_value = attempts
                with self.subTest(attempts=attempts), self.assertRaisesRegex(RuntimeError, "5 attempts per UTC day"):
                    live_execution.validate_live_risk_limits()

    def test_increasing_cap_uses_existing_attempts_without_reset(self):
        with (
            patch.object(live_execution, "MAX_LIVE_TRADES_PER_DAY", 60),
            patch.object(live_execution, "live_trade_count_today", return_value=30) as count,
            patch.object(live_execution, "realized_live_profit_loss_today", return_value=Decimal("0")),
        ):
            live_execution.validate_live_risk_limits()
            count.assert_called_once()
            count.return_value = 60
            with self.assertRaisesRegex(RuntimeError, "Daily live trade limit reached"):
                live_execution.validate_live_risk_limits()

    def test_zero_disables_attempt_cap_and_losses_do_not_stop_trading(self):
        with (
            patch.object(live_execution, "MAX_LIVE_TRADES_PER_DAY", 0),
            patch.object(live_execution, "live_trade_count_today", return_value=1000),
            patch.object(live_execution, "realized_live_profit_loss_today", return_value=Decimal("0")) as profit,
        ):
            live_execution.validate_live_risk_limits()
            profit.assert_called_once()
            profit.return_value = Decimal("-100.1469")
            live_execution.validate_live_risk_limits()

    def test_corrupt_recorded_pnl_still_blocks_trading(self):
        with (
            patch.object(live_execution, "MAX_LIVE_TRADES_PER_DAY", 0),
            patch.object(live_execution, "realized_live_profit_loss_today", side_effect=RuntimeError("invalid recorded P/L")),
            self.assertRaisesRegex(RuntimeError, "invalid recorded P/L"),
        ):
            live_execution.validate_live_risk_limits()

    def test_obsolete_daily_loss_environment_setting_has_no_effect(self):
        code = (
            "from decimal import Decimal; from unittest.mock import patch; import live_execution; "
            "guard = patch.object(live_execution, 'realized_live_profit_loss_today', return_value=Decimal('-100.1469')); "
            "guard.start(); live_execution.validate_live_risk_limits(); print('allowed')"
        )
        for old_limit in ("10", "0", "invalid"):
            with self.subTest(old_limit=old_limit):
                env = {
                    **os.environ,
                    "PYTHONPATH": str(ROOT / "src"),
                    "KALSHI_MAX_LIVE_TRADES_PER_DAY": "0",
                    "KALSHI_MAX_DAILY_LIVE_LOSS": old_limit,
                }
                result = subprocess.run(
                    [sys.executable, "-c", code], cwd=ROOT, env=env,
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("allowed", result.stdout.strip())

    def test_disabling_cap_keeps_market_deduplication_and_budget_checks(self):
        row = {field: "" for field in live_execution.FIELDNAMES}
        row.update(timestamp=datetime.now(timezone.utc).isoformat(), ticker="ALREADY", side="YES")
        live_execution.write_live_trade_rows([row])
        create = Mock()
        with patch.object(live_execution, "MAX_LIVE_TRADES_PER_DAY", 0), redirect_stdout(io.StringIO()):
            self.assertFalse(live_execution.place_live_trade(
                ticker="ALREADY", side="YES", prediction="UP", entry_price="0.80", create_order_fn=create,
            ))
            with self.assertRaisesRegex(ValueError, "exceeds.*budget"):
                live_execution.place_live_trade(
                    ticker="NEW", side="YES", prediction="UP", entry_price="0.80",
                    contracts=2, trade_budget="1", create_order_fn=create,
                )
        create.assert_not_called()
        self.assertEqual(1, len(live_execution.read_live_trade_rows()))


class DashboardDailyLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        root = Path(self.tmpdir.name)
        patcher = patch.multiple(
            dashboard, ROOT=root, LOG_DIR=root / "logs",
            BOT_PROCESSES={}, BOT_TRADE_BUDGETS={}, BOT_DAILY_LIVE_LIMITS={},
            MAX_LIVE_TRADES_PER_DAY=30,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stopped_live_bots_report_default_cap_but_paper_does_not(self):
        for status in dashboard.bot_statuses():
            if status["mode"] == "live":
                self.assertEqual(30, status["dailyLiveOrderLimit"])
            else:
                self.assertNotIn("dailyLiveOrderLimit", status)

    def test_both_live_runners_receive_and_report_exact_selected_cap(self):
        for bot_id in (live_execution.LEGACY_LIVE_BOT_ID, live_execution.DUAL_LIVE_BOT_ID):
            for limit in ("0", "1", "60"):
                dashboard.BOT_PROCESSES.clear()
                process = Mock(pid=12345)
                process.poll.return_value = None
                with (
                    self.subTest(bot=bot_id, limit=limit),
                    patch("dashboard.subprocess.Popen", return_value=process) as start,
                    patch("dashboard.time.sleep"), redirect_stdout(io.StringIO()),
                ):
                    result, status = dashboard.start_bot(bot_id, daily_live_order_limit=limit)
                    self.assertEqual(200, status)
                    self.assertTrue(result["ok"])
                    self.assertEqual(limit, start.call_args.kwargs["env"]["KALSHI_MAX_LIVE_TRADES_PER_DAY"])
                    live_status = next(row for row in dashboard.bot_statuses() if row["id"] == bot_id)
                    self.assertEqual(int(limit), live_status["dailyLiveOrderLimit"])

    def test_bad_or_paper_only_setting_never_starts_a_process(self):
        for limit in ("", "-1", "1.5", True, "NaN", "unlimited"):
            with self.subTest(limit=limit), patch("dashboard.subprocess.Popen") as start:
                result, status = dashboard.start_bot(live_execution.DUAL_LIVE_BOT_ID, daily_live_order_limit=limit)
                self.assertEqual(400, status)
                self.assertFalse(result["ok"])
                start.assert_not_called()
        for bot_id in ("btc15_paper", "btc15_dual_paper", "scalp_paper"):
            with self.subTest(bot=bot_id), patch("dashboard.subprocess.Popen") as start:
                _, status = dashboard.start_bot(bot_id, daily_live_order_limit="0")
                self.assertEqual(400, status)
                start.assert_not_called()

    def test_running_bot_cannot_change_cap_without_restart(self):
        bot_id = live_execution.DUAL_LIVE_BOT_ID
        running = Mock(pid=12345)
        running.poll.return_value = None
        dashboard.BOT_PROCESSES[bot_id] = running
        dashboard.BOT_DAILY_LIVE_LIMITS[bot_id] = 60
        with patch("dashboard.subprocess.Popen") as start, redirect_stdout(io.StringIO()):
            for value in ("0", "30", "61"):
                with self.subTest(limit=value):
                    result, status = dashboard.start_bot(bot_id, daily_live_order_limit=value)
                    self.assertEqual(409, status)
                    self.assertIn("Stop", result["message"])
            self.assertEqual(200, dashboard.start_bot(bot_id, daily_live_order_limit="60")[1])
            self.assertEqual(200, dashboard.start_bot(bot_id)[1])
            self.assertEqual(60, dashboard.BOT_DAILY_LIVE_LIMITS[bot_id])
            start.assert_not_called()

    def test_failed_start_does_not_publish_selected_cap(self):
        process = Mock()
        process.poll.return_value = 1
        with patch("dashboard.subprocess.Popen", return_value=process), patch("dashboard.time.sleep"), redirect_stdout(io.StringIO()):
            _, status = dashboard.start_bot(live_execution.DUAL_LIVE_BOT_ID, daily_live_order_limit="0")
        self.assertEqual(409, status)
        self.assertEqual({}, dashboard.BOT_DAILY_LIVE_LIMITS)

    def test_post_handler_forwards_explicit_zero(self):
        body = b'{"botId":"btc15_dual_live","tradeBudget":"1","dailyLiveOrderLimit":0}'
        handler = SimpleNamespace(
            path="/api/bots/start", headers={"Content-Length": str(len(body))}, rfile=io.BytesIO(body),
        )
        with patch.object(dashboard, "start_bot", return_value=({"ok": True}, 200)) as start, patch.object(dashboard, "json_response"):
            dashboard.DashboardHandler.do_POST(handler)
        start.assert_called_once_with("btc15_dual_live", trade_budget="1", daily_live_order_limit=0)


if __name__ == "__main__":
    unittest.main()
