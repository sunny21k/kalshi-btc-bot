import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scalp_strategy import (
    build_candle,
    choose_scalp_entry,
    choose_scalp_exit,
)


def candle(start, open_price, close_price):
    return build_candle(start, [Decimal(open_price), Decimal(close_price)])


class ScalpStrategyTests(unittest.TestCase):
    def test_buys_yes_on_5s_up_continuation_with_15s_confirmation(self):
        result = choose_scalp_entry(
            [
                candle(1, "100", "101"),
                candle(6, "101", "103"),
                candle(11, "103", "106"),
            ],
            [candle(1, "100", "106")],
            yes_ask=Decimal("0.70"),
            no_ask=Decimal("0.30"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("BUY YES", result["decision"])
        self.assertEqual("YES", result["side"])

    def test_buys_no_on_5s_down_continuation_with_15s_confirmation(self):
        result = choose_scalp_entry(
            [
                candle(1, "106", "105"),
                candle(6, "105", "103"),
                candle(11, "103", "100"),
            ],
            [candle(1, "106", "100")],
            yes_ask=Decimal("0.30"),
            no_ask=Decimal("0.70"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("BUY NO", result["decision"])
        self.assertEqual("NO", result["side"])

    def test_waits_when_candle_bodies_shrink(self):
        result = choose_scalp_entry(
            [
                candle(1, "100", "105"),
                candle(6, "105", "108"),
                candle(11, "108", "109"),
            ],
            [candle(1, "100", "109")],
            yes_ask=Decimal("0.70"),
            no_ask=Decimal("0.30"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("WAIT", result["decision"])
        self.assertEqual("entry candle body shrinking", result["reason"])

    def test_trailing_profit_exit(self):
        position = {
            "side": "YES",
            "entry_price": Decimal("0.50"),
            "contracts": 100,
            "peak_profit": Decimal("50"),
        }

        result = choose_scalp_exit(
            position,
            [candle(1, "100", "101"), candle(6, "101", "102")],
            yes_bid=Decimal("0.85"),
            no_bid=Decimal("0.15"),
            trailing_activation=Decimal("50"),
            trailing_floor=Decimal("35"),
            stop_loss=Decimal("20"),
        )

        self.assertEqual("SELL", result["decision"])
        self.assertEqual("trailing profit floor", result["reason"])

    def test_stop_loss_exit(self):
        position = {
            "side": "NO",
            "entry_price": Decimal("0.70"),
            "contracts": 100,
            "peak_profit": Decimal("0"),
        }

        result = choose_scalp_exit(
            position,
            [candle(1, "100", "99"), candle(6, "99", "98")],
            yes_bid=Decimal("0.80"),
            no_bid=Decimal("0.40"),
            trailing_activation=Decimal("50"),
            trailing_floor=Decimal("35"),
            stop_loss=Decimal("20"),
        )

        self.assertEqual("SELL", result["decision"])
        self.assertEqual("stop loss", result["reason"])


if __name__ == "__main__":
    unittest.main()
