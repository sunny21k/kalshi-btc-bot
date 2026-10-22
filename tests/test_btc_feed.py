import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import btc_feed


class BtcFeedTests(unittest.TestCase):
    def test_returns_price_and_closes_socket(self):
        ws = Mock()
        ws.recv.side_effect = [
            json.dumps({"type": "subscriptions"}),
            json.dumps({"type": "ticker", "price": "81467.95"}),
        ]
        with (
            patch("btc_feed.websocket.create_connection", return_value=ws) as connect,
            patch("btc_feed.time.monotonic", side_effect=[100, 101, 102]),
        ):
            self.assertEqual(81467.95, btc_feed.get_btc_price())

        self.assertEqual(10, connect.call_args.kwargs["timeout"])
        self.assertEqual([call(9), call(8)], ws.settimeout.call_args_list)
        ws.close.assert_called_once()

    def test_total_deadline_applies_even_if_non_ticker_messages_arrive(self):
        ws = Mock()
        ws.recv.return_value = json.dumps({"type": "subscriptions"})
        with (
            patch("btc_feed.websocket.create_connection", return_value=ws),
            patch("btc_feed.time.monotonic", side_effect=[100, 104, 110]),
        ):
            with self.assertRaises(WebSocketTimeoutException):
                btc_feed.get_btc_price()

        ws.recv.assert_called_once()
        ws.close.assert_called_once()

    def test_closes_socket_on_network_failure(self):
        for operation, error in (
            ("send", ConnectionResetError("connection reset")),
            ("recv", WebSocketConnectionClosedException("remote host lost")),
            ("recv", WebSocketTimeoutException("read timed out")),
        ):
            with self.subTest(operation=operation, error=type(error).__name__):
                ws = Mock()
                getattr(ws, operation).side_effect = error
                with (
                    patch("btc_feed.websocket.create_connection", return_value=ws),
                    patch("btc_feed.time.monotonic", return_value=100),
                ):
                    with self.assertRaises(type(error)):
                        btc_feed.get_btc_price()
                ws.close.assert_called_once()

    def test_empty_receive_is_treated_as_a_closed_connection(self):
        ws = Mock()
        ws.recv.return_value = ""
        with (
            patch("btc_feed.websocket.create_connection", return_value=ws),
            patch("btc_feed.time.monotonic", return_value=100),
        ):
            with self.assertRaises(WebSocketConnectionClosedException):
                btc_feed.get_btc_price()
        ws.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
