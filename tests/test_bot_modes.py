import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import DEFAULT, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bot


class BotModeTests(unittest.TestCase):
    def test_no_only_filter_applies_to_paper_entries(self):
        scenarios = [
            (False, "YES", [82340, 82341, 82342], 180),
            (False, "NO", [82300, 82299, 82298], 180),
            (True, "YES", [82340, 82341, 82342], 180),
            (True, "NO", [82300, 82299, 82298], 180),
            (False, "YES", [82400, 82401, 82402], 500),
            (True, "YES", [82400, 82401, 82402], 500),
        ]
        for live_enabled, side, prices, seconds_remaining in scenarios:
            with self.subTest(live=live_enabled, side=side, seconds=seconds_remaining):
                with (
                    patch.multiple(
                        bot,
                        LIVE_TRADING_ENABLED=live_enabled,
                        get_btc_price=DEFAULT,
                        get_current_market=DEFAULT,
                        get_seconds_remaining=DEFAULT,
                        get_orderbook=DEFAULT,
                        log_market_data=DEFAULT,
                        log_shadow_signal=DEFAULT,
                        record_paper_trade=DEFAULT,
                        place_live_trade=DEFAULT,
                    ) as mocks,
                    patch("bot.time.sleep", side_effect=[None, None, KeyboardInterrupt]),
                    redirect_stdout(io.StringIO()),
                ):
                    mocks["get_btc_price"].side_effect = prices
                    mocks["get_current_market"].return_value = {
                        "ticker": "KXBTC15M-TEST",
                        "floor_strike": "82323.36",
                    }
                    mocks["get_seconds_remaining"].return_value = seconds_remaining
                    mocks["get_orderbook"].return_value = {
                        "orderbook_fp": {
                            "yes_dollars": [["0.78" if side == "YES" else "0.20", 10]],
                            "no_dollars": [["0.78" if side == "NO" else "0.20", 10]],
                        },
                    }

                    bot.main()

                    blocked = not live_enabled and side == "YES"
                    signal = mocks["log_shadow_signal"].call_args.kwargs["trade_signal"]
                    self.assertEqual("WAIT" if blocked else f"BUY {side}", signal["decision"])
                    if blocked:
                        self.assertEqual("15m paper test is NO-only", signal["reason"])
                    for name, expected in (
                        ("record_paper_trade", not live_enabled and not blocked),
                        ("place_live_trade", live_enabled),
                    ):
                        self.assertEqual(int(expected), mocks[name].call_count)
                        if expected:
                            self.assertEqual(side, mocks[name].call_args.kwargs["side"])


if __name__ == "__main__":
    unittest.main()
