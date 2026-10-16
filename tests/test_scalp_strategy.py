import csv
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import scalp_execution
from scalp_strategy import (
    build_candle,
    choose_scalp_entry,
    choose_scalp_exit,
)


def candle(start, open_price, close_price):
    return build_candle(start, [Decimal(open_price), Decimal(close_price)])


class ScalpStrategyTests(unittest.TestCase):
    def test_buys_yes_on_5s_up_momentum_with_15s_confirmation(self):
        result = choose_scalp_entry(
            [
                candle(1, "100", "101"),
                candle(6, "103", "101"),
                candle(11, "103", "106"),
            ],
            [candle(1, "100", "106")],
            yes_ask=Decimal("0.70"),
            no_ask=Decimal("0.30"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("BUY YES", result["decision"])
        self.assertEqual("YES", result["side"])

    def test_buys_no_on_5s_down_momentum_with_15s_confirmation(self):
        result = choose_scalp_entry(
            [
                candle(1, "106", "105"),
                candle(6, "103", "105"),
                candle(11, "103", "100"),
            ],
            [candle(1, "106", "100")],
            yes_ask=Decimal("0.30"),
            no_ask=Decimal("0.70"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("BUY NO", result["decision"])
        self.assertEqual("NO", result["side"])

    def test_waits_when_15s_confirmation_disagrees(self):
        result = choose_scalp_entry(
            [
                candle(1, "100", "105"),
                candle(6, "105", "108"),
                candle(11, "108", "109"),
            ],
            [candle(1, "109", "100")],
            yes_ask=Decimal("0.70"),
            no_ask=Decimal("0.30"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("WAIT", result["decision"])
        self.assertEqual("no candle continuation", result["reason"])

    def test_can_disable_yes_entries(self):
        result = choose_scalp_entry(
            [
                candle(1, "100", "101"),
                candle(6, "101", "102"),
                candle(11, "102", "103"),
            ],
            [candle(1, "100", "103")],
            yes_ask=Decimal("0.60"),
            no_ask=Decimal("0.40"),
            spread=Decimal("0.02"),
            allowed_sides=("NO",),
        )

        self.assertEqual("WAIT", result["decision"])

    def test_allows_nearly_full_price_range(self):
        result = choose_scalp_entry(
            [
                candle(1, "106", "105"),
                candle(6, "103", "105"),
                candle(11, "103", "100"),
            ],
            [candle(1, "106", "100")],
            yes_ask=Decimal("0.01"),
            no_ask=Decimal("0.99"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("BUY NO", result["decision"])

    def test_waits_when_entry_candle_body_is_shrinking(self):
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

    def test_waits_when_latest_candle_is_flat(self):
        result = choose_scalp_entry(
            [
                candle(1, "100", "101"),
                candle(6, "101", "102"),
                candle(11, "102", "102"),
            ],
            [candle(1, "100", "102")],
            yes_ask=Decimal("0.70"),
            no_ask=Decimal("0.30"),
            spread=Decimal("0.02"),
        )

        self.assertEqual("WAIT", result["decision"])
        self.assertEqual("no candle continuation", result["reason"])

    def test_trailing_profit_exit(self):
        position = {
            "side": "YES",
            "entry_price": Decimal("0.50"),
            "contracts": 1,
            "peak_profit": Decimal("0.05"),
        }

        result = choose_scalp_exit(
            position,
            [candle(1, "100", "101"), candle(6, "101", "102")],
            yes_bid=Decimal("0.54"),
            no_bid=Decimal("0.15"),
            trailing_activation=Decimal("0.03"),
            trailing_giveback=Decimal("0.01"),
            stop_loss=Decimal("0.03"),
        )

        self.assertEqual("SELL", result["decision"])
        self.assertEqual("trailing giveback", result["reason"])

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
            trailing_giveback=Decimal("15"),
            stop_loss=Decimal("20"),
        )

        self.assertEqual("SELL", result["decision"])
        self.assertEqual("stop loss", result["reason"])


class ScalpExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_trade_file = scalp_execution.SCALP_TRADE_FILE
        scalp_execution.SCALP_TRADE_FILE = os.path.join(
            self.tmpdir.name,
            "scalp_paper_trades.csv",
        )
        self.addCleanup(
            setattr,
            scalp_execution,
            "SCALP_TRADE_FILE",
            self.original_trade_file,
        )

    def read_rows(self):
        with open(scalp_execution.SCALP_TRADE_FILE, "r", newline="") as file:
            return list(csv.DictReader(file))

    def test_open_and_close_rows_include_opened_and_closed_times(self):
        position = scalp_execution.open_position(
            ticker="KXBTC15M-SCALP",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.45"),
            contracts=1,
            reason="test entry",
        )
        scalp_execution.close_position(
            position,
            exit_price=Decimal("0.55"),
            profit_loss=Decimal("0.10"),
            peak_profit=Decimal("0.12"),
            reason="test exit",
        )

        rows = self.read_rows()
        self.assertEqual(scalp_execution.FIELDNAMES, list(rows[0].keys()))
        self.assertEqual("OPEN", rows[0]["event"])
        self.assertEqual(rows[0]["timestamp"], rows[0]["opened_at"])
        self.assertEqual("", rows[0]["closed_at"])
        self.assertEqual("CLOSE", rows[1]["event"])
        self.assertEqual(rows[0]["opened_at"], rows[1]["opened_at"])
        self.assertEqual(rows[1]["timestamp"], rows[1]["closed_at"])


if __name__ == "__main__":
    unittest.main()
