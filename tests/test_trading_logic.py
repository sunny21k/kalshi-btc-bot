import csv
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import paper_execution
import prediction_tracker
import live_execution
from bot import get_yes_quote
from strategy import (
    calculate_edge,
    estimate_probability,
    make_decision,
    make_late_momentum_decision,
)


class PaperExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_trade_file = paper_execution.TRADE_FILE
        paper_execution.TRADE_FILE = os.path.join(self.tmpdir.name, "paper_trades.csv")
        self.addCleanup(setattr, paper_execution, "TRADE_FILE", self.original_trade_file)

    def read_rows(self):
        with open(paper_execution.TRADE_FILE, "r", newline="") as file:
            return list(csv.DictReader(file))

    def test_paper_budget_rounds_down_to_whole_contracts_without_exceeding_100(self):
        for price, expected in (("0.80", 125), ("0.83", 120), ("0.75", 133), ("0.92", 108), ("0.005", 20000), ("1.00", 100)):
            with self.subTest(price=price):
                contracts = paper_execution.contracts_for_budget(price)
                self.assertEqual(expected, contracts)
                cost = Decimal(price) * contracts
                self.assertLessEqual(cost, Decimal("100"))
                self.assertGreater(cost + Decimal(price), Decimal("100"))

    def test_paper_budget_rejects_invalid_prices_and_insufficient_budgets(self):
        for price in ("0", "-0.01", "1.01", "NaN", "Infinity"):
            with self.subTest(price=price), self.assertRaises(ValueError):
                paper_execution.contracts_for_budget(price)
        for budget in ("0", "-1", "0.79", "NaN", "Infinity"):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                paper_execution.contracts_for_budget("0.80", budget=budget)

    def test_budget_sized_trades_log_and_settle_the_full_contract_quantity(self):
        for side, result in (("YES", "YES"), ("NO", "NO"), ("NO", "YES")):
            ticker = f"{side}-{result}"
            paper_execution.record_paper_trade(
                ticker=ticker,
                side=side,
                prediction="UP" if side == "YES" else "DOWN",
                entry_price="0.80",
                model_probability="0.80",
                edge="0",
                contracts=paper_execution.contracts_for_budget("0.80"),
            )
        results = {"YES-YES": "YES", "NO-NO": "NO", "NO-YES": "YES"}
        self.assertEqual(3, paper_execution.update_paper_trade_results(results.get))
        rows = {row["ticker"]: row for row in self.read_rows()}
        for ticker, profit in (("YES-YES", "25.0000"), ("NO-NO", "25.0000"), ("NO-YES", "-100.0000")):
            self.assertEqual("125", rows[ticker]["contracts"])
            self.assertEqual("100.0000", rows[ticker]["cost"])
            self.assertEqual(profit, rows[ticker]["profit_loss"])

    def test_record_paper_trade_uses_canonical_schema_and_prevents_duplicates(self):
        recorded = paper_execution.record_paper_trade(
            ticker="KXBTC15M-TEST",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.58"),
            model_probability=Decimal("0.6596"),
            edge=Decimal("0.0796"),
            contracts=1,
        )
        duplicate = paper_execution.record_paper_trade(
            ticker="KXBTC15M-TEST",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.58"),
            model_probability=Decimal("0.6596"),
            edge=Decimal("0.0796"),
            contracts=1,
        )

        rows = self.read_rows()
        self.assertTrue(recorded)
        self.assertFalse(duplicate)
        self.assertEqual(1, len(rows))
        self.assertEqual(paper_execution.FIELDNAMES, list(rows[0].keys()))
        self.assertTrue(rows[0]["trade_id"].startswith("paper-"))
        self.assertEqual("YES", rows[0]["side"])
        self.assertEqual("0.5800", rows[0]["entry_price"])
        self.assertEqual("0.5800", rows[0]["cost"])
        self.assertEqual("", rows[0]["actual_result"])
        self.assertEqual("", rows[0]["profit_loss"])
        self.assertEqual("", rows[0]["correct"])

    def test_settlement_updates_only_unsettled_rows_and_uses_purchased_side(self):
        paper_execution.write_trade_rows([
            {
                "timestamp": "t1",
                "trade_id": "paper-yes",
                "ticker": "YES-WIN",
                "side": "YES",
                "prediction": "UP",
                "entry_price": "0.5800",
                "model_probability": "0.6596",
                "edge": "0.0796",
                "contracts": "1",
                "cost": "0.5800",
                "actual_result": "",
                "profit_loss": "",
                "correct": "",
            },
            {
                "timestamp": "t2",
                "trade_id": "paper-no",
                "ticker": "NO-WIN",
                "side": "NO",
                "prediction": "DOWN",
                "entry_price": "0.4600",
                "model_probability": "0.5416",
                "edge": "0.0816",
                "contracts": "1",
                "cost": "0.4600",
                "actual_result": "",
                "profit_loss": "",
                "correct": "",
            },
            {
                "timestamp": "t3",
                "trade_id": "paper-already",
                "ticker": "ALREADY",
                "side": "YES",
                "prediction": "UP",
                "entry_price": "0.2500",
                "model_probability": "0.7000",
                "edge": "0.4500",
                "contracts": "1",
                "cost": "0.2500",
                "actual_result": "NO",
                "profit_loss": "-0.2500",
                "correct": "False",
            },
        ])

        updated = paper_execution.update_paper_trade_results(
            lambda ticker: {"YES-WIN": "YES", "NO-WIN": "NO"}.get(ticker)
        )

        rows = {row["ticker"]: row for row in self.read_rows()}
        self.assertEqual(2, updated)
        self.assertEqual("0.4200", rows["YES-WIN"]["profit_loss"])
        self.assertEqual("True", rows["YES-WIN"]["correct"])
        self.assertEqual("0.5400", rows["NO-WIN"]["profit_loss"])
        self.assertEqual("True", rows["NO-WIN"]["correct"])
        self.assertEqual("-0.2500", rows["ALREADY"]["profit_loss"])


class LiveExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_live_trade_file = live_execution.LIVE_TRADE_FILE
        live_execution.LIVE_TRADE_FILE = os.path.join(self.tmpdir.name, "live_trades.csv")
        self.addCleanup(
            setattr,
            live_execution,
            "LIVE_TRADE_FILE",
            self.original_live_trade_file,
        )

    def read_rows(self):
        with open(live_execution.LIVE_TRADE_FILE, "r", newline="") as file:
            return list(csv.DictReader(file))

    def live_row(self, **overrides):
        row = {field: "" for field in live_execution.FIELDNAMES}
        row.update({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trade_id": "live-test",
            "ticker": "KXBTC15M-LIVE",
            "side": "YES",
            "prediction": "UP",
            "entry_price": "0.8000",
            "contracts": "1",
            "max_cost": "0.8000",
            "order_side": "bid",
            "order_price": "0.8000",
            "client_order_id": "client",
            "status": "executed",
            "order_id": "order",
            "response": "{}",
            "error": "",
        })
        row.update(overrides)
        return row

    def test_live_yes_trade_records_order_without_duplicate(self):
        calls = []

        def fake_create_order(ticker, **kwargs):
            calls.append((ticker, kwargs))
            return {"order": {"order_id": "ord_123", "status": "resting"}}

        recorded = live_execution.place_live_trade(
            ticker="KXBTC15M-LIVE",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.80"),
            contracts=1,
            exchange_index=2,
            create_order_fn=fake_create_order,
        )
        duplicate = live_execution.place_live_trade(
            ticker="KXBTC15M-LIVE",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.80"),
            contracts=1,
            exchange_index=2,
            create_order_fn=fake_create_order,
        )

        rows = self.read_rows()
        self.assertTrue(recorded)
        self.assertFalse(duplicate)
        self.assertEqual(1, len(calls))
        self.assertEqual("bid", calls[0][1]["side"])
        self.assertEqual(Decimal("0.8000"), Decimal(calls[0][1]["price"]))
        self.assertEqual(1, len(rows))
        self.assertEqual(live_execution.FIELDNAMES, list(rows[0].keys()))
        self.assertTrue(rows[0]["trade_id"].startswith("live-"))
        self.assertTrue(rows[0]["client_order_id"].startswith("btc15m-live-"))
        self.assertEqual("YES", rows[0]["side"])
        self.assertEqual("0.8000", rows[0]["entry_price"])
        self.assertEqual("0.8000", rows[0]["max_cost"])
        self.assertEqual("ord_123", rows[0]["order_id"])

    def test_live_no_trade_sends_equivalent_yes_ask_order(self):
        calls = []

        def fake_create_order(ticker, **kwargs):
            calls.append((ticker, kwargs))
            return {"order": {"order_id": "ord_456", "status": "executed"}}

        recorded = live_execution.place_live_trade(
            ticker="KXBTC15M-NO",
            side="NO",
            prediction="DOWN",
            entry_price=Decimal("0.82"),
            contracts=1,
            create_order_fn=fake_create_order,
        )

        rows = self.read_rows()
        self.assertTrue(recorded)
        self.assertEqual("ask", calls[0][1]["side"])
        self.assertEqual(Decimal("0.1800"), Decimal(calls[0][1]["price"]))
        self.assertEqual("NO", rows[0]["side"])
        self.assertEqual("0.8200", rows[0]["entry_price"])
        self.assertEqual("ask", rows[0]["order_side"])
        self.assertEqual("0.1800", rows[0]["order_price"])

    def test_live_duplicate_guard_blocks_failed_attempts_too(self):
        live_execution.write_live_trade_rows([
            self.live_row(
                ticker="KXBTC15M-FAILED",
                status="ERROR",
                error="bad request",
            )
        ])

        recorded = live_execution.place_live_trade(
            ticker="KXBTC15M-FAILED",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.80"),
            contracts=1,
            create_order_fn=lambda ticker, **kwargs: {},
        )

        self.assertFalse(recorded)

    def test_live_settlement_updates_unsettled_rows(self):
        live_execution.write_live_trade_rows([
            {
                "timestamp": "t1",
                "trade_id": "live-yes",
                "ticker": "LIVE-YES",
                "side": "YES",
                "prediction": "UP",
                "entry_price": "0.8000",
                "contracts": "1",
                "max_cost": "0.8000",
                "order_side": "bid",
                "order_price": "0.8000",
                "client_order_id": "c1",
                "status": "executed",
                "order_id": "o1",
                "actual_result": "",
                "profit_loss": "",
                "correct": "",
                "response": "{}",
                "error": "",
            },
            {
                "timestamp": "t2",
                "trade_id": "live-no",
                "ticker": "LIVE-NO",
                "side": "NO",
                "prediction": "DOWN",
                "entry_price": "0.8200",
                "contracts": "1",
                "max_cost": "0.8200",
                "order_side": "ask",
                "order_price": "0.1800",
                "client_order_id": "c2",
                "status": "executed",
                "order_id": "o2",
                "actual_result": "",
                "profit_loss": "",
                "correct": "",
                "response": "{}",
                "error": "",
            },
        ])

        updated = live_execution.update_live_trade_results(
            lambda ticker: {"LIVE-YES": "YES", "LIVE-NO": "YES"}.get(ticker),
            get_fills_fn=lambda order_id, *, ticker: [{
                "order_id": order_id,
                "ticker": ticker,
                "count_fp": "1.00",
                "yes_price_dollars": "0.8000" if order_id == "o1" else "0.1800",
                "no_price_dollars": "0.2000" if order_id == "o1" else "0.8200",
                "fee_cost": "0.0000",
            }],
        )

        rows = {row["ticker"]: row for row in self.read_rows()}
        self.assertEqual(2, updated)
        self.assertEqual("0.2000", rows["LIVE-YES"]["profit_loss"])
        self.assertEqual("True", rows["LIVE-YES"]["correct"])
        self.assertEqual("-0.8200", rows["LIVE-NO"]["profit_loss"])
        self.assertEqual("False", rows["LIVE-NO"]["correct"])

    def test_live_risk_blocks_after_thirty_trades_today(self):
        live_execution.write_live_trade_rows([
            self.live_row(ticker=f"KXBTC15M-LIVE-{index}")
            for index in range(30)
        ])

        with self.assertRaisesRegex(RuntimeError, "Daily live trade limit reached"):
            live_execution.place_live_trade(
                ticker="KXBTC15M-LIVE-NEW",
                side="YES",
                prediction="UP",
                entry_price=Decimal("0.80"),
                contracts=1,
                create_order_fn=lambda ticker, **kwargs: {},
            )

    def test_live_risk_blocks_after_daily_loss_limit(self):
        live_execution.write_live_trade_rows([
            self.live_row(
                ticker="KXBTC15M-LOSS",
                actual_result="NO",
                profit_loss="-10.0000",
                correct="False",
            )
        ])

        with self.assertRaisesRegex(RuntimeError, "Daily live loss limit reached"):
            live_execution.place_live_trade(
                ticker="KXBTC15M-LIVE-NEW",
                side="YES",
                prediction="UP",
                entry_price=Decimal("0.80"),
                contracts=1,
                create_order_fn=lambda ticker, **kwargs: {},
            )

    def test_live_risk_ignores_previous_day_rows(self):
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        calls = []
        live_execution.write_live_trade_rows([
            self.live_row(
                ticker=f"KXBTC15M-YESTERDAY-{index}",
                timestamp=yesterday.isoformat(),
                profit_loss="-10.0000",
            )
            for index in range(30)
        ])

        recorded = live_execution.place_live_trade(
            ticker="KXBTC15M-TODAY",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.80"),
            contracts=1,
            create_order_fn=lambda ticker, **kwargs: calls.append(kwargs) or {},
        )

        self.assertTrue(recorded)
        self.assertEqual(1, len(calls))


class StrategyTests(unittest.TestCase):
    def test_orderbook_quotes_use_dollar_probability_units(self):
        quote = get_yes_quote({
            "orderbook_fp": {
                "yes_dollars": [["0.42", 10]],
                "no_dollars": [["0.54", 10]],
            }
        })

        self.assertEqual(
            (
                Decimal("0.42"),
                Decimal("0.46"),
                Decimal("0.54"),
                Decimal("0.58"),
                Decimal("0.04"),
            ),
            quote,
        )

    def test_orderbook_quote_falls_back_to_market_prices(self):
        quote = get_yes_quote(
            {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}},
            {
                "yes_bid_dollars": "0.7800",
                "yes_ask_dollars": "0.8000",
                "no_bid_dollars": "0.2000",
                "no_ask_dollars": "0.2200",
            },
        )

        self.assertEqual(
            (
                Decimal("0.7800"),
                Decimal("0.8000"),
                Decimal("0.2000"),
                Decimal("0.2200"),
                Decimal("0.0200"),
            ),
            quote,
        )

    def test_edge_uses_dollar_probability_units(self):
        self.assertEqual(
            Decimal("0.0796"),
            calculate_edge(Decimal("0.6596"), Decimal("0.58")),
        )

    def test_down_probability_increases_with_movement_and_can_buy_no(self):
        probability = estimate_probability("DOWN", Decimal("-0.0408"))
        self.assertEqual(Decimal("0.5816"), probability)
        self.assertEqual(
            "BUY NO",
            make_decision("DOWN", probability, Decimal("0.60"), Decimal("0.46")),
        )

    def test_late_momentum_buys_yes_when_above_target_in_price_band(self):
        result = make_late_momentum_decision(
            btc_price=Decimal("82335"),
            target_price=Decimal("82323.36"),
            seconds_remaining=Decimal("180"),
            yes_ask=Decimal("0.80"),
            no_ask=Decimal("0.20"),
            spread=Decimal("0.02"),
            recent_prices=[
                Decimal("82325"),
                Decimal("82330"),
                Decimal("82335"),
            ],
            confirmation_count=3,
        )

        self.assertEqual("BUY YES", result["decision"])
        self.assertEqual("YES", result["side"])
        self.assertEqual("UP", result["prediction"])
        self.assertEqual(Decimal("0.80"), result["entry_price"])

    def test_late_momentum_buys_no_when_below_target_in_price_band(self):
        result = make_late_momentum_decision(
            btc_price=Decimal("82300"),
            target_price=Decimal("82323.36"),
            seconds_remaining=Decimal("180"),
            yes_ask=Decimal("0.20"),
            no_ask=Decimal("0.82"),
            spread=Decimal("0.02"),
            recent_prices=[
                Decimal("82320"),
                Decimal("82310"),
                Decimal("82300"),
            ],
            confirmation_count=3,
        )

        self.assertEqual("BUY NO", result["decision"])
        self.assertEqual("NO", result["side"])
        self.assertEqual("DOWN", result["prediction"])
        self.assertEqual(Decimal("0.82"), result["entry_price"])

    def test_late_momentum_buys_with_strong_five_minute_rule(self):
        result = make_late_momentum_decision(
            btc_price=Decimal("82380"),
            target_price=Decimal("82323.36"),
            seconds_remaining=Decimal("290"),
            yes_ask=Decimal("0.84"),
            no_ask=Decimal("0.16"),
            spread=Decimal("0.02"),
            recent_prices=[
                Decimal("82340"),
                Decimal("82360"),
                Decimal("82380"),
            ],
            confirmation_count=3,
        )

        self.assertEqual("BUY YES", result["decision"])
        self.assertEqual("strong_5m_50", result["strategy_name"])
        self.assertEqual("strong 5-minute $50 rule passed", result["reason"])

    def test_strong_rule_uses_five_minute_boundary_for_both_sides(self):
        for side, direction in (("YES", 1), ("NO", -1)):
            for seconds, allowed in (("300", True), ("300.001", False), ("350", False), ("240", True)):
                with self.subTest(side=side, seconds=seconds):
                    result = make_late_momentum_decision(
                        btc_price=Decimal("100000") + direction * Decimal("50"),
                        target_price=Decimal("100000"),
                        seconds_remaining=Decimal(seconds),
                        yes_ask=Decimal("0.84") if side == "YES" else Decimal("0.18"),
                        no_ask=Decimal("0.84") if side == "NO" else Decimal("0.18"),
                        spread=Decimal("0.02"),
                        recent_prices=[
                            Decimal("100000") + direction * Decimal(distance)
                            for distance in ("40", "45", "50")
                        ],
                        confirmation_count=3,
                    )
                    self.assertEqual(f"BUY {side}" if allowed else "WAIT", result["decision"])
                    if allowed:
                        self.assertEqual("strong_5m_50", result["strategy_name"])

    def test_strong_five_minute_rule_still_requires_fifty_dollar_difference(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                result = make_late_momentum_decision(
                    btc_price=Decimal("100000") + direction * Decimal("49.99"),
                    target_price=Decimal("100000"),
                    seconds_remaining=Decimal("270"),
                    yes_ask=Decimal("0.80"),
                    no_ask=Decimal("0.80"),
                    confirmation_count=3,
                )
                self.assertEqual("WAIT", result["decision"])
                self.assertEqual("BTC is less than $50 from target", result["reason"])

    def test_late_momentum_buys_yes_with_early_nine_minute_rule(self):
        result = make_late_momentum_decision(
            btc_price=Decimal("82400"),
            target_price=Decimal("82323.36"),
            seconds_remaining=Decimal("530"),
            yes_ask=Decimal("0.86"),
            no_ask=Decimal("0.14"),
            spread=Decimal("0.02"),
            recent_prices=[
                Decimal("82350"),
                Decimal("82375"),
                Decimal("82400"),
            ],
            confirmation_count=3,
        )

        self.assertEqual("BUY YES", result["decision"])
        self.assertEqual("early_up_9m_70", result["strategy_name"])
        self.assertEqual("early 9-minute $70 up rule passed", result["reason"])

    def test_late_rule_uses_lower_max_price_than_strong_rule(self):
        result = make_late_momentum_decision(
            btc_price=Decimal("82340"),
            target_price=Decimal("82323.36"),
            seconds_remaining=Decimal("180"),
            yes_ask=Decimal("0.88"),
            no_ask=Decimal("0.12"),
            spread=Decimal("0.02"),
            recent_prices=[
                Decimal("82325"),
                Decimal("82330"),
                Decimal("82340"),
            ],
            confirmation_count=3,
        )

        self.assertEqual("WAIT", result["decision"])
        self.assertEqual("YES ask outside allowed price band", result["reason"])

    def test_late_momentum_waits_outside_time_price_or_difference_filters(self):
        self.assertEqual(
            "WAIT",
            make_late_momentum_decision(
                btc_price=Decimal("82335"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("241"),
                yes_ask=Decimal("0.80"),
                no_ask=Decimal("0.20"),
            )["decision"],
        )

    def test_late_momentum_waits_on_final_seconds_wide_spread_or_bad_momentum(self):
        self.assertEqual(
            "inside final 30 seconds",
            make_late_momentum_decision(
                btc_price=Decimal("82380"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("30"),
                yes_ask=Decimal("0.84"),
                no_ask=Decimal("0.16"),
                spread=Decimal("0.02"),
                recent_prices=[
                    Decimal("82340"),
                    Decimal("82360"),
                    Decimal("82380"),
                ],
                confirmation_count=3,
            )["reason"],
        )
        self.assertEqual(
            "spread wider than 3 cents",
            make_late_momentum_decision(
                btc_price=Decimal("82380"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("180"),
                yes_ask=Decimal("0.84"),
                no_ask=Decimal("0.16"),
                spread=Decimal("0.04"),
                recent_prices=[
                    Decimal("82340"),
                    Decimal("82360"),
                    Decimal("82380"),
                ],
                confirmation_count=3,
            )["reason"],
        )
        self.assertEqual(
            "recent BTC momentum does not confirm UP",
            make_late_momentum_decision(
                btc_price=Decimal("82380"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("180"),
                yes_ask=Decimal("0.84"),
                no_ask=Decimal("0.16"),
                spread=Decimal("0.02"),
                recent_prices=[
                    Decimal("82390"),
                    Decimal("82385"),
                    Decimal("82380"),
                ],
                confirmation_count=3,
            )["reason"],
        )

    def test_late_momentum_waits_without_confirmation_or_after_chase(self):
        self.assertEqual(
            "price threshold not confirmed for 3 polls",
            make_late_momentum_decision(
                btc_price=Decimal("82380"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("180"),
                yes_ask=Decimal("0.84"),
                no_ask=Decimal("0.16"),
                spread=Decimal("0.02"),
                recent_prices=[
                    Decimal("82340"),
                    Decimal("82360"),
                    Decimal("82380"),
                ],
                confirmation_count=2,
            )["reason"],
        )
        self.assertEqual(
            "ask moved up too fast",
            make_late_momentum_decision(
                btc_price=Decimal("82380"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("180"),
                yes_ask=Decimal("0.84"),
                no_ask=Decimal("0.16"),
                spread=Decimal("0.02"),
                recent_prices=[
                    Decimal("82340"),
                    Decimal("82360"),
                    Decimal("82380"),
                ],
                previous_entry_price=Decimal("0.78"),
                confirmation_count=3,
            )["reason"],
        )
        self.assertEqual(
            "WAIT",
            make_late_momentum_decision(
                btc_price=Decimal("82360"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("300"),
                yes_ask=Decimal("0.80"),
                no_ask=Decimal("0.20"),
            )["decision"],
        )
        self.assertEqual(
            "WAIT",
            make_late_momentum_decision(
                btc_price=Decimal("82328"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("180"),
                yes_ask=Decimal("0.80"),
                no_ask=Decimal("0.20"),
            )["decision"],
        )
        self.assertEqual(
            "WAIT",
            make_late_momentum_decision(
                btc_price=Decimal("82335"),
                target_price=Decimal("82323.36"),
                seconds_remaining=Decimal("180"),
                yes_ask=Decimal("0.93"),
                no_ask=Decimal("0.20"),
            )["decision"],
        )


class PredictionTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_data_file = prediction_tracker.DATA_FILE
        prediction_tracker.DATA_FILE = os.path.join(self.tmpdir.name, "market_data.csv")
        self.addCleanup(setattr, prediction_tracker, "DATA_FILE", self.original_data_file)

    def test_completed_predictions_keep_first_actionable_signal_per_ticker(self):
        with open(prediction_tracker.DATA_FILE, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["timestamp", "ticker", "signal"])
            writer.writeheader()
            writer.writerow({"timestamp": "1", "ticker": "T1", "signal": "NEUTRAL"})
            writer.writerow({"timestamp": "2", "ticker": "T1", "signal": "UP"})
            writer.writerow({"timestamp": "3", "ticker": "T1", "signal": "DOWN"})
            writer.writerow({"timestamp": "4", "ticker": "T2", "signal": "DOWN"})

        self.assertEqual(
            {"T1": "UP", "T2": "DOWN"},
            prediction_tracker.get_completed_predictions(),
        )


if __name__ == "__main__":
    unittest.main()
