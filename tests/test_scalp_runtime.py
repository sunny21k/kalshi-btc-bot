import io
import ssl
import sys
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import DEFAULT, call, patch

from requests.exceptions import ReadTimeout
from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import scalp_bot


class ScalpRuntimeTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.multiple(
            scalp_bot,
            initialize_scalp_file=DEFAULT,
            get_btc_price=DEFAULT,
            get_current_market=DEFAULT,
            get_orderbook=DEFAULT,
            get_yes_quote=DEFAULT,
            get_seconds_remaining=DEFAULT,
            closed_candles=DEFAULT,
            choose_scalp_entry=DEFAULT,
            choose_scalp_exit=DEFAULT,
            open_position=DEFAULT,
            close_position=DEFAULT,
        )
        self.mocks = patcher.start()
        self.addCleanup(patcher.stop)
        self.mocks["get_btc_price"].return_value = Decimal("81467.95")
        self.mocks["get_current_market"].return_value = {"ticker": "KXBTC15M-TEST"}
        self.mocks["get_orderbook"].return_value = {}
        self.mocks["get_yes_quote"].return_value = tuple(
            Decimal(value) for value in ("0.49", "0.50", "0.50", "0.51", "0.01")
        )
        self.mocks["get_seconds_remaining"].return_value = 300
        self.mocks["closed_candles"].return_value = []
        self.mocks["choose_scalp_entry"].return_value = {
            "decision": "BUY YES",
            "side": "YES",
            "prediction": "UP",
            "entry_price": Decimal("0.50"),
            "reason": "test momentum",
        }
        self.position = {
            "trade_id": "scalp-test",
            "opened_at": "2026-10-17T02:00:00+00:00",
            "ticker": "KXBTC15M-TEST",
            "side": "YES",
            "contracts": 1,
            "entry_price": Decimal("0.50"),
            "peak_profit": Decimal("0"),
        }
        self.mocks["open_position"].return_value = self.position

    def test_retries_network_failures_with_bounded_backoff_then_resumes(self):
        self.mocks["get_btc_price"].side_effect = [
            WebSocketConnectionClosedException("remote host lost"),
            WebSocketTimeoutException("ticker timed out"),
            ReadTimeout("Kalshi timed out"),
            ConnectionResetError("connection reset"),
            TimeoutError("socket timed out"),
            ssl.SSLError("TLS connection lost"),
            ReadTimeout("still unavailable"),
            Decimal("81467.95"),
        ]
        output = io.StringIO()
        with (
            patch("scalp_bot.time.sleep", side_effect=[None] * 7 + [KeyboardInterrupt]) as sleep,
            redirect_stdout(output),
        ):
            scalp_bot.main()

        self.assertEqual(
            [call(delay) for delay in (1, 2, 4, 8, 16, 30, 30, float(scalp_bot.POLL_SECONDS))],
            sleep.call_args_list,
        )
        self.mocks["open_position"].assert_called_once()
        self.assertIn("Market data connection restored.", output.getvalue())

    def test_orderbook_timeout_preserves_position_and_peak_until_exit(self):
        self.mocks["get_orderbook"].side_effect = [{}, {}, ReadTimeout("timed out"), {}]
        self.mocks["choose_scalp_exit"].side_effect = [
            {
                "decision": "HOLD",
                "exit_price": Decimal("0.55"),
                "current_profit": Decimal("0.05"),
                "peak_profit": Decimal("0.05"),
                "reason": "hold",
            },
            {
                "decision": "SELL",
                "exit_price": Decimal("0.54"),
                "current_profit": Decimal("0.04"),
                "peak_profit": Decimal("0.05"),
                "reason": "trailing giveback",
            },
        ]
        with (
            patch("scalp_bot.time.sleep", side_effect=[None, None, None, KeyboardInterrupt]),
            redirect_stdout(io.StringIO()),
        ):
            scalp_bot.main()

        self.mocks["open_position"].assert_called_once()
        self.mocks["choose_scalp_entry"].assert_called_once()
        self.mocks["close_position"].assert_called_once_with(
            self.position,
            exit_price=Decimal("0.54"),
            profit_loss=Decimal("0.04"),
            peak_profit=Decimal("0.05"),
            reason="trailing giveback",
        )
        self.assertEqual(Decimal("0.05"), self.position["peak_profit"])
        for exit_call in self.mocks["choose_scalp_exit"].call_args_list:
            self.assertIs(self.position, exit_call.args[0])

    def test_ctrl_c_during_retry_stops_cleanly(self):
        self.mocks["get_btc_price"].side_effect = ConnectionResetError("connection reset")
        output = io.StringIO()
        with (
            patch("scalp_bot.time.sleep", side_effect=KeyboardInterrupt),
            redirect_stdout(output),
        ):
            scalp_bot.main()

        self.mocks["open_position"].assert_not_called()
        self.assertIn("Scalp bot stopped.", output.getvalue())

    def test_unexpected_errors_are_not_hidden_as_network_retries(self):
        self.mocks["get_btc_price"].side_effect = ValueError("invalid price")
        with redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "invalid price"):
                scalp_bot.main()


if __name__ == "__main__":
    unittest.main()
