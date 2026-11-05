import csv
import io
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import dashboard
import live_execution
import paper_execution
import prediction_tracker
from run_lock import RunLock


def empty_sync():
    return dict(running=False, stopping=False, startedAt=None, completedAt=None, summary=None, error=None)


def summary():
    return dict(paperSettled=1, dualPaperSettled=1, directionPaperSettled=0, liveSettled=1, predictionsRecorded=1,
                errors=[], errorCount=0, checked=4, stopped=False)


class ResultsRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.paper_file = str(self.root / "paper.csv")
        self.dual_file = str(self.root / "dual.csv")
        self.live_file = str(self.root / "live.csv")
        self.market_file = str(self.root / "market.csv")
        self.result_file = str(self.root / "results.csv")
        for module, name, value in (
            (paper_execution, "TRADE_FILE", self.paper_file),
            (live_execution, "LIVE_TRADE_FILE", self.live_file),
            (prediction_tracker, "DUAL_TRADE_FILE", self.dual_file),
            (prediction_tracker, "DIRECTION_TRADE_FILE", str(self.root / "direction.csv")),
            (prediction_tracker, "DATA_FILE", self.market_file),
            (prediction_tracker, "RESULTS_FILE", self.result_file),
            (prediction_tracker, "RunLock", lambda name: RunLock(str(self.root / name))),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with open(self.market_file, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["timestamp", "ticker", "signal"])
            writer.writeheader()
            writer.writerow(dict(timestamp="1", ticker="SHARED", signal="UP"))
        self.record_paper("SHARED")
        self.record_paper("SHARED", trade_file=self.dual_file)
        row = {field: "" for field in live_execution.FIELDNAMES}
        row.update(trade_id="live-1", ticker="SHARED", side="YES", order_id="order-1",
                   contracts="1", submitted_count="1", filled_count="1.00", entry_price="0.8000")
        live_execution.write_live_trade_rows([row])
        self.fills = [{"order_id": "order-1", "ticker": "SHARED", "count_fp": "1.00",
                       "yes_price_dollars": "0.8000", "fee_cost": "0.0200"}]

    def record_paper(self, ticker, *, trade_file=None):
        return paper_execution.record_paper_trade(
            ticker=ticker, side="YES", prediction="UP", entry_price="0.80",
            model_probability="0.85", edge="0.05", trade_file=trade_file,
        )

    def refresh(self, *, result="YES", fills=None):
        fills_fn = Mock(return_value=self.fills if fills is None else fills)
        runner = partial(live_execution.update_live_trade_results, get_fills_fn=fills_fn)
        with (
            patch.object(prediction_tracker, "get_market_result", return_value=result) as markets,
            patch.object(prediction_tracker, "update_live_trade_results", side_effect=runner),
            patch.object(live_execution, "create_order") as create,
            redirect_stdout(io.StringIO()),
        ):
            result = prediction_tracker.refresh_results()
        create.assert_not_called()
        return result, markets, fills_fn

    def test_refresh_updates_fees_net_pnl_both_paper_ledgers_and_predictions(self):
        result, markets, _ = self.refresh()
        self.assertEqual(summary(), result)
        markets.assert_called_once_with("SHARED")
        live = live_execution.read_live_trade_rows()[0]
        self.assertEqual("0.0200", live["fees_paid"])
        self.assertEqual("0.1800", live["profit_loss"])
        self.assertEqual("ACTUAL", live["pnl_basis"])
        for path in (self.paper_file, self.dual_file):
            self.assertEqual("0.2000", paper_execution.read_trade_rows(path)[0]["profit_loss"])
        with open(self.result_file, newline="") as file:
            self.assertEqual("True", next(csv.DictReader(file))["correct"])

    def test_direction_paper_ledger_is_settled_using_the_same_cached_result(self):
        path = str(self.root / "direction.csv")
        self.record_paper("SHARED", trade_file=path)
        result, markets, _ = self.refresh()
        self.assertEqual(1, result["directionPaperSettled"])
        self.assertEqual("0.2000", paper_execution.read_trade_rows(path)[0]["profit_loss"])
        markets.assert_called_once_with("SHARED")

    def test_pending_market_updates_fees_without_fabricating_settlement(self):
        result, _, _ = self.refresh(result=None)
        self.assertEqual(0, result["liveSettled"])
        self.assertEqual(0, result["paperSettled"])
        self.assertEqual(0, result["errorCount"])
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("0.0200", row["fees_paid"])
        self.assertEqual("", row["profit_loss"])
        self.assertEqual("", row["actual_result"])

    def test_missing_fees_are_reported_and_net_pnl_stays_unknown(self):
        result, _, _ = self.refresh(fills=[{**self.fills[0], "fee_cost": None}])
        self.assertEqual(1, result["errorCount"])
        self.assertIn("fees unavailable", result["errors"][0]["message"])
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("", row["fees_paid"])
        self.assertEqual("", row["profit_loss"])
        self.assertEqual(1, result["paperSettled"])

    def test_a_failed_live_lookup_does_not_block_paper_or_prediction_updates(self):
        failing = partial(live_execution.update_live_trade_results, get_fills_fn=Mock(side_effect=TimeoutError("exchange timeout")))
        with (
            patch.object(prediction_tracker, "get_market_result", return_value="YES"),
            patch.object(prediction_tracker, "update_live_trade_results", side_effect=failing),
            redirect_stdout(io.StringIO()),
        ):
            result = prediction_tracker.refresh_results()
        self.assertEqual(1, result["errorCount"])
        self.assertEqual("liveSettled", result["errors"][0]["stage"])
        self.assertEqual(1, result["paperSettled"])
        self.assertEqual(1, result["dualPaperSettled"])
        self.assertEqual(1, result["predictionsRecorded"])
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("1.00", row["filled_count"])
        self.assertEqual("", row["profit_loss"])

    def test_whole_stage_failure_still_refreshes_other_stages(self):
        with (
            patch.object(prediction_tracker, "get_market_result", return_value="YES"),
            patch.object(prediction_tracker, "update_live_trade_results", side_effect=ValueError("bad ledger")),
            redirect_stdout(io.StringIO()),
        ):
            result = prediction_tracker.refresh_results()
        self.assertEqual(1, result["errorCount"])
        self.assertEqual(1, result["paperSettled"])
        self.assertEqual(1, result["predictionsRecorded"])

    def test_cli_and_dashboard_cannot_run_overlapping_refreshes(self):
        with RunLock(str(self.root / "prediction_tracker")), patch.object(prediction_tracker, "get_market_result") as markets:
            with self.assertRaisesRegex(RuntimeError, "already locked"):
                prediction_tracker.refresh_results()
            blocked = RunLock(str(self.root / "prediction_tracker"))
            with self.assertRaises(RuntimeError):
                blocked.__enter__()
            self.assertIsNone(blocked.file)
        markets.assert_not_called()

    def test_cli_still_runs_the_same_refresh_pipeline(self):
        with patch.object(prediction_tracker, "refresh_results", return_value=summary()) as refresh, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, prediction_tracker.main())
        refresh.assert_called_once_with()
        self.assertIn("Live trades settled: 1", output.getvalue())

    def test_paper_trade_appended_during_lookup_survives_refresh(self):
        def lookup(ticker):
            self.record_paper("NEW")
            return "YES"

        self.assertEqual(1, paper_execution.update_paper_trade_results(lookup))
        rows = paper_execution.read_trade_rows()
        self.assertEqual(["SHARED", "NEW"], [row["ticker"] for row in rows])
        self.assertEqual("0.2000", rows[0]["profit_loss"])
        self.assertEqual("", rows[1]["actual_result"])

    def test_paper_refresh_does_not_overwrite_another_completed_settlement(self):
        def lookup(ticker):
            rows = paper_execution.read_trade_rows()
            rows[0].update(actual_result="NO", profit_loss="-0.8000", correct="False")
            paper_execution.write_trade_rows(rows)
            return "YES"

        self.assertEqual(0, paper_execution.update_paper_trade_results(lookup))
        self.assertEqual("-0.8000", paper_execution.read_trade_rows()[0]["profit_loss"])

    def test_paper_lookup_failure_does_not_block_later_rows(self):
        self.record_paper("GOOD")
        errors = []

        def lookup(ticker):
            if ticker == "SHARED":
                raise TimeoutError("failed")
            return "YES"

        with redirect_stdout(io.StringIO()):
            self.assertEqual(1, paper_execution.update_paper_trade_results(lookup, on_error=errors.append))
        self.assertEqual(1, len(errors))
        self.assertEqual("", paper_execution.read_trade_rows()[0]["actual_result"])
        self.assertEqual("YES", paper_execution.read_trade_rows()[1]["actual_result"])

    def test_failed_atomic_paper_write_keeps_original_file(self):
        original = Path(self.paper_file).read_bytes()
        with self.assertRaises(ValueError):
            paper_execution.write_trade_rows([{"unexpected-column": "bad"}])
        self.assertEqual(original, Path(self.paper_file).read_bytes())
        self.assertEqual([], list(self.root.glob(".paper-trades-*")))

    def test_live_refresh_cannot_erase_a_newer_verified_settlement(self):
        def lookup(order_id, **kwargs):
            rows = live_execution.read_live_trade_rows()
            rows[0].update(pnl_basis="ACTUAL", profit_loss="0.1800", fees_paid="0.0200", actual_result="YES")
            live_execution.write_live_trade_rows(rows)
            raise TimeoutError("stale worker failed")

        with redirect_stdout(io.StringIO()):
            live_execution.update_live_trade_results(lambda ticker: "YES", get_fills_fn=lookup)
        self.assertEqual("0.1800", live_execution.read_live_trade_rows()[0]["profit_loss"])

    def test_live_results_are_visible_before_the_next_order_lookup(self):
        rows = live_execution.read_live_trade_rows()
        rows.append({**rows[0], "trade_id": "live-2", "order_id": "order-2", "ticker": "SECOND"})
        live_execution.write_live_trade_rows(rows)

        def fills(order_id, *, ticker):
            if order_id == "order-2":
                current = live_execution.read_live_trade_rows()
                self.assertEqual("0.1800", current[0]["profit_loss"])
                self.assertEqual("0.0200", current[0]["fees_paid"])
                self.assertEqual("", current[1]["profit_loss"])
            return [{**self.fills[0], "order_id": order_id, "ticker": ticker}]

        with redirect_stdout(io.StringIO()):
            self.assertEqual(2, live_execution.update_live_trade_results(lambda ticker: "YES", get_fills_fn=fills))

    def test_paper_results_are_visible_before_the_next_market_lookup(self):
        self.record_paper("SECOND")

        def lookup(ticker):
            if ticker == "SECOND":
                current = paper_execution.read_trade_rows()
                self.assertEqual("0.2000", current[0]["profit_loss"])
                self.assertEqual("", current[1]["profit_loss"])
            return "YES"

        with redirect_stdout(io.StringIO()):
            self.assertEqual(2, paper_execution.update_paper_trade_results(lookup))

    def test_cancel_after_first_saved_check_skips_the_rest_and_keeps_progress(self):
        stop = threading.Event()
        snapshots = []
        fills = Mock(return_value=self.fills)

        def progress(value):
            snapshots.append(value)
            if value["checked"] == 1:
                self.assertEqual("0.1800", live_execution.read_live_trade_rows()[0]["profit_loss"])
                stop.set()

        with (
            patch.object(prediction_tracker, "get_market_result", return_value="YES"),
            patch.object(prediction_tracker, "update_live_trade_results", side_effect=partial(live_execution.update_live_trade_results, get_fills_fn=fills)),
            redirect_stdout(io.StringIO()),
        ):
            result = prediction_tracker.refresh_results(should_stop=stop.is_set, on_progress=progress)
        self.assertTrue(result["stopped"])
        self.assertEqual(1, result["liveSettled"])
        self.assertEqual(1, result["checked"])
        self.assertEqual(0, result["paperSettled"])
        self.assertEqual("", paper_execution.read_trade_rows()[0]["actual_result"])
        self.assertEqual([], snapshots[0]["errors"])
        fills.assert_called_once()

    def test_cancel_during_fill_lookup_saves_fees_without_more_exchange_requests(self):
        stop = threading.Event()

        def fills(order_id, **kwargs):
            stop.set()
            return self.fills

        with (
            patch.object(prediction_tracker, "get_market_result") as market,
            patch.object(prediction_tracker, "update_live_trade_results", side_effect=partial(live_execution.update_live_trade_results, get_fills_fn=fills)),
            redirect_stdout(io.StringIO()),
        ):
            result = prediction_tracker.refresh_results(should_stop=stop.is_set)
        market.assert_not_called()
        self.assertTrue(result["stopped"])
        self.assertEqual(0, result["liveSettled"])
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("0.0200", row["fees_paid"])
        self.assertEqual("", row["profit_loss"])

    def test_keyboard_interrupt_preserves_saved_live_results_and_releases_tracker_lock(self):
        rows = live_execution.read_live_trade_rows()
        rows.append({**rows[0], "trade_id": "live-2", "order_id": "order-2", "ticker": "SECOND"})
        live_execution.write_live_trade_rows(rows)
        fills = Mock(side_effect=[self.fills, KeyboardInterrupt])
        with (
            patch.object(prediction_tracker, "get_market_result", return_value="YES"),
            patch.object(prediction_tracker, "update_live_trade_results", side_effect=partial(live_execution.update_live_trade_results, get_fills_fn=fills)),
            redirect_stdout(io.StringIO()),
        ):
            result = prediction_tracker.refresh_results()
        self.assertTrue(result["stopped"])
        self.assertEqual(1, result["liveSettled"])
        self.assertEqual(1, result["checked"])
        current = live_execution.read_live_trade_rows()
        self.assertEqual("0.1800", current[0]["profit_loss"])
        self.assertEqual("", current[1]["profit_loss"])
        with RunLock(str(self.root / "prediction_tracker")):
            pass

    def test_paper_interrupt_keeps_previously_saved_settlements(self):
        self.record_paper("SECOND")
        with redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            paper_execution.update_paper_trade_results(Mock(side_effect=["YES", KeyboardInterrupt]))
        current = paper_execution.read_trade_rows()
        self.assertEqual("0.2000", current[0]["profit_loss"])
        self.assertEqual("", current[1]["profit_loss"])

    def test_cancel_before_start_does_not_call_exchange(self):
        with patch.object(prediction_tracker, "get_market_result") as market:
            result = prediction_tracker.refresh_results(should_stop=lambda: True)
        self.assertTrue(result["stopped"])
        self.assertEqual(0, result["checked"])
        market.assert_not_called()

    def test_prediction_refresh_stops_between_rows_and_keeps_written_results(self):
        with open(self.market_file, "a", newline="") as file:
            csv.writer(file).writerow(["2", "SECOND", "UP"])
        stop = threading.Event()
        lookup = Mock(return_value="YES")
        with redirect_stdout(io.StringIO()):
            count = prediction_tracker.track_completed_markets(
                get_result_fn=lookup, should_stop=stop.is_set, on_progress=lambda _: stop.set(),
            )
        self.assertEqual(1, count)
        lookup.assert_called_once_with("SHARED")
        with open(self.result_file, newline="") as file:
            self.assertEqual(["SHARED"], [row["ticker"] for row in csv.DictReader(file)])


class DashboardRefreshTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.multiple(dashboard, RESULT_SYNC=empty_sync(), RESULT_SYNC_CANCEL=threading.Event())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_refresh_is_background_deduplicated_and_does_not_touch_bots(self):
        started, release = threading.Event(), threading.Event()
        workers = []
        real_thread = threading.Thread

        def refresh(**kwargs):
            started.set()
            if not release.wait(5):
                raise TimeoutError("test worker not released")
            return summary()

        def make_thread(**kwargs):
            worker = real_thread(**kwargs)
            workers.append(worker)
            return worker

        with (
            patch.object(dashboard, "refresh_results", side_effect=refresh) as refresh_fn,
            patch.object(dashboard.threading, "Thread", side_effect=make_thread),
            patch.object(dashboard, "stop_all_bots") as stop,
            patch.object(dashboard.subprocess, "Popen") as launch,
            patch.object(dashboard.os, "killpg") as kill,
            redirect_stdout(io.StringIO()),
        ):
            try:
                response, status = dashboard.start_result_sync()
                self.assertEqual(202, status)
                self.assertTrue(response["resultSync"]["running"])
                self.assertTrue(started.wait(2))
                self.assertTrue(dashboard.result_sync_status()["running"])
                self.assertEqual(202, dashboard.start_result_sync()[1])
                self.assertEqual(1, len(workers))
            finally:
                release.set()
                for worker in workers:
                    worker.join(5)
                    self.assertFalse(worker.is_alive())
            refresh_fn.assert_called_once()
            stop.assert_not_called()
            launch.assert_not_called()
            kill.assert_not_called()
        final = dashboard.result_sync_status()
        self.assertFalse(final["running"])
        self.assertIsNotNone(final["completedAt"])
        self.assertEqual(summary(), final["summary"])
        self.assertIsNone(final["error"])

    def test_worker_failure_is_visible_and_clears_busy_state(self):
        dashboard.RESULT_SYNC["running"] = True
        with patch.object(dashboard, "refresh_results", side_effect=RuntimeError("tracker already locked")), redirect_stdout(io.StringIO()):
            dashboard.run_result_sync()
        status = dashboard.result_sync_status()
        self.assertFalse(status["running"])
        self.assertEqual("tracker already locked", status["error"])
        self.assertIsNone(status["summary"])

    def test_thread_start_failure_returns_error_without_leaving_busy_state(self):
        with patch.object(dashboard.threading, "Thread") as worker:
            worker.return_value.start.side_effect = RuntimeError("cannot start worker")
            response, code = dashboard.start_result_sync()
        self.assertEqual(500, code)
        self.assertFalse(response["ok"])
        self.assertFalse(dashboard.result_sync_status()["running"])

    def test_post_routes_only_to_results_refresh(self):
        handler = SimpleNamespace(path="/api/results/refresh", headers={}, rfile=io.BytesIO(b""))
        with (
            patch.object(dashboard, "start_result_sync", return_value=({"ok": True}, 202)) as refresh,
            patch.object(dashboard, "start_bot") as bot,
            patch.object(dashboard, "json_response") as respond,
        ):
            dashboard.DashboardHandler.do_POST(handler)
        refresh.assert_called_once_with()
        respond.assert_called_once_with(handler, {"ok": True}, status=202)
        bot.assert_not_called()

    def test_status_get_is_read_only_and_payload_exposes_refresh_state(self):
        handler = SimpleNamespace(path="/api/results/status")
        with patch.object(dashboard, "json_response") as respond, patch.object(dashboard, "refresh_results") as refresh:
            dashboard.DashboardHandler.do_GET(handler)
        respond.assert_called_once_with(handler, empty_sync())
        refresh.assert_not_called()
        with patch.object(dashboard, "read_csv", return_value=[]):
            self.assertEqual(empty_sync(), dashboard.build_payload()["resultSync"])

    def test_cancel_updates_only_refresh_state_and_does_not_stop_bots(self):
        dashboard.RESULT_SYNC["running"] = True
        dashboard.publish_result_progress({**summary(), "checked": 1})
        with patch.object(dashboard, "stop_all_bots") as stop, patch.object(dashboard.os, "killpg") as kill:
            response, code = dashboard.stop_result_sync()
        self.assertEqual(202, code)
        self.assertTrue(response["resultSync"]["stopping"])
        self.assertTrue(dashboard.RESULT_SYNC_CANCEL.is_set())
        self.assertTrue(dashboard.result_sync_status()["running"])
        self.assertEqual(1, dashboard.result_sync_status()["summary"]["checked"])
        stop.assert_not_called()
        kill.assert_not_called()

    def test_cancel_idle_job_and_start_again_do_not_reuse_old_cancellation(self):
        self.assertEqual(200, dashboard.stop_result_sync()[1])
        self.assertFalse(dashboard.RESULT_SYNC_CANCEL.is_set())
        dashboard.RESULT_SYNC_CANCEL.set()
        with patch.object(dashboard.threading, "Thread"), redirect_stdout(io.StringIO()):
            self.assertEqual(202, dashboard.start_result_sync()[1])
        self.assertFalse(dashboard.RESULT_SYNC_CANCEL.is_set())
        self.assertFalse(dashboard.result_sync_status()["stopping"])

    def test_canceled_worker_publishes_saved_counts_and_allows_another_refresh(self):
        dashboard.RESULT_SYNC.update(running=True, stopping=True)
        result = {**summary(), "stopped": True}
        with patch.object(dashboard, "refresh_results", return_value=result) as refresh, redirect_stdout(io.StringIO()):
            dashboard.run_result_sync()
        self.assertIn("should_stop", refresh.call_args.kwargs)
        self.assertIn("on_progress", refresh.call_args.kwargs)
        self.assertFalse(dashboard.result_sync_status()["running"])
        self.assertFalse(dashboard.result_sync_status()["stopping"])
        self.assertTrue(dashboard.result_sync_status()["summary"]["stopped"])

    def test_cancel_endpoint_does_not_route_to_bot_stop(self):
        handler = SimpleNamespace(path="/api/results/cancel", headers={}, rfile=io.BytesIO(b""))
        with (
            patch.object(dashboard, "stop_result_sync", return_value=({"ok": True}, 202)) as cancel,
            patch.object(dashboard, "stop_bot") as stop,
            patch.object(dashboard, "json_response") as respond,
        ):
            dashboard.DashboardHandler.do_POST(handler)
        cancel.assert_called_once_with()
        stop.assert_not_called()
        respond.assert_called_once_with(handler, {"ok": True}, status=202)


if __name__ == "__main__":
    unittest.main()
