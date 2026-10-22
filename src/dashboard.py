import csv
import json
import mimetypes
import os
import signal
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from live_execution import live_filled_count, live_fill_status
from paper_execution import DUAL_TRADE_FILE, PAPER_TRADE_BUDGET


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DASHBOARD_DIST = ROOT / "dashboard" / "dist"
PAPER_FILE = DATA_DIR / "paper_trades.csv"
DUAL_PAPER_FILE = ROOT / DUAL_TRADE_FILE
LIVE_FILE = DATA_DIR / "live_trades.csv"
SHADOW_FILE = DATA_DIR / "shadow_signals.csv"
SCALP_FILE = DATA_DIR / "scalp_paper_trades.csv"
LOG_DIR = DATA_DIR / "bot_logs"
BOT_PROCESSES = {}
STARTUP_CHECK_SECONDS = 0.35


BOTS = {
    "btc15_paper": {
        "name": "15m Paper Bot (NO Only)",
        "script": "bot.py",
        "mode": "paper",
        "description": (
            "Paper tests NO trades only on 15-minute BTC Kalshi markets using "
            "the target-distance rules, momentum checks, and spread filter. "
            f"Up to ${PAPER_TRADE_BUDGET:.0f} per trade in whole contracts, once per market."
        ),
        "env": {"KALSHI_LIVE_TRADING": "false"},
    },
    "btc15_dual_paper": {
        "name": "15m YES/NO Paper Bot",
        "script": "dual_paper_bot.py",
        "mode": "paper",
        "description": (
            "Paper trades YES above the target or NO below it: $10 distance "
            "within 4 minutes, or $50 within 5 minutes. "
            f"Up to ${PAPER_TRADE_BUDGET:.0f} per trade, once per market, "
            "with the existing price, momentum, and spread checks."
        ),
        "env": {"KALSHI_LIVE_TRADING": "false"},
    },
    "btc15_live": {
        "name": "15m Live Bot",
        "script": "bot.py",
        "mode": "live",
        "description": (
            "Same 15-minute strategy, but submits real Kalshi orders with "
            "live risk limits, daily cap, and live_trades.csv logging."
        ),
        "env": {"KALSHI_LIVE_TRADING": "true"},
    },
    "scalp_paper": {
        "name": "Scalp Paper Bot",
        "script": "scalp_bot.py",
        "mode": "paper",
        "description": (
            "Fast paper-only bot using 5-second momentum with 15-second confirmation, "
            "NO-only entries by default, trailing giveback exits, and a 3-cent stop."
        ),
        "env": {},
    },
}


def decimal_or_zero(value):
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", newline="") as file:
        return list(csv.DictReader(file))


def money(value):
    return f"{Decimal(value):.4f}"


def pct(part, total):
    if not total:
        return None
    return float(Decimal(part) / Decimal(total) * Decimal("100"))


def side_stats(rows):
    settled = [row for row in rows if row.get("actual_result") in ("YES", "NO")]
    wins = [
        row
        for row in settled
        if row.get("correct") == "True"
        or (
            row.get("correct") in (None, "")
            and row.get("side") == row.get("actual_result")
        )
    ]
    profit_loss = sum(decimal_or_zero(row.get("profit_loss")) for row in settled)
    return {
        "total": len(rows),
        "settled": len(settled),
        "winRate": pct(len(wins), len(settled)),
        "profitLoss": money(profit_loss),
    }


def bucket_stats(rows, field):
    buckets = defaultdict(list)
    for row in rows:
        buckets[row.get(field) or "unknown"].append(row)
    return {key: side_stats(value) for key, value in sorted(buckets.items())}


def trade_stats(rows, *, cost_field):
    valid_rows = [row for row in rows if not row.get("error")]
    settled = [row for row in valid_rows if row.get("actual_result") in ("YES", "NO")]
    wins = [
        row
        for row in settled
        if row.get("correct") == "True"
        or (
            row.get("correct") in (None, "")
            and row.get("side") == row.get("actual_result")
        )
    ]
    total_invested = sum(decimal_or_zero(row.get(cost_field)) for row in settled)
    total_profit_loss = sum(decimal_or_zero(row.get("profit_loss")) for row in settled)
    return {
        "total": len(valid_rows),
        "settled": len(settled),
        "unsettled": len(valid_rows) - len(settled),
        "wins": len(wins),
        "losses": len(settled) - len(wins),
        "winRate": pct(len(wins), len(settled)),
        "totalInvested": money(total_invested),
        "profitLoss": money(total_profit_loss),
        "roi": (
            float(total_profit_loss / total_invested * Decimal("100"))
            if total_invested
            else None
        ),
        "yes": side_stats([row for row in valid_rows if row.get("side") == "YES"]),
        "no": side_stats([row for row in valid_rows if row.get("side") == "NO"]),
        "byStrategy": bucket_stats(valid_rows, "strategy_name"),
        "byTime": bucket_stats(valid_rows, "seconds_remaining"),
        "recent": valid_rows[-20:][::-1],
    }


def live_trade_stats(rows):
    trades = [
        row for row in rows
        if not row.get("error")
        and row.get("side") in ("YES", "NO")
        and (live_filled_count(row) or Decimal("0")) > 0
    ]
    stats = trade_stats(trades, cost_field="fill_cost")
    stats["recent"] = [
        {**row, "fill_status": live_fill_status(row)}
        for row in reversed(rows[-20:])
        if row.get("side") in ("YES", "NO")
    ]
    return stats


def shadow_stats(rows):
    reasons = Counter(row.get("reason") or "unknown" for row in rows)
    decisions = Counter(row.get("decision") or "unknown" for row in rows)
    return {
        "total": len(rows),
        "decisions": dict(decisions.most_common(12)),
        "blockedReasons": dict(reasons.most_common(12)),
        "recent": rows[-30:][::-1],
    }


def scalp_stats(rows):
    valid_rows = [
        row for row in rows
        if not row.get("error")
        and row.get("event") in ("OPEN", "CLOSE")
        and str(row.get("trade_id", "")).startswith("scalp-")
    ]
    opens = [row for row in valid_rows if row.get("event") == "OPEN"]
    closes = [row for row in valid_rows if row.get("event") == "CLOSE"]
    closed_ids = {row.get("trade_id") for row in closes}
    open_positions = [
        row for row in opens if row.get("trade_id") not in closed_ids
    ]
    wins = [row for row in closes if decimal_or_zero(row.get("profit_loss")) > 0]
    total_invested = sum(decimal_or_zero(row.get("cost")) for row in opens)
    total_profit_loss = sum(decimal_or_zero(row.get("profit_loss")) for row in closes)
    peak_profit = sum(decimal_or_zero(row.get("peak_profit")) for row in closes)
    reasons = Counter(row.get("reason") or "unknown" for row in valid_rows)

    return {
        "total": len(opens),
        "closed": len(closes),
        "open": len(open_positions),
        "wins": len(wins),
        "losses": len(closes) - len(wins),
        "winRate": pct(len(wins), len(closes)),
        "totalInvested": money(total_invested),
        "profitLoss": money(total_profit_loss),
        "peakProfit": money(peak_profit),
        "byReason": dict(reasons.most_common(12)),
        "recent": valid_rows[-30:][::-1],
    }


def build_payload():
    return {
        "paper": trade_stats(read_csv(PAPER_FILE), cost_field="cost"),
        "dualPaper": trade_stats(read_csv(DUAL_PAPER_FILE), cost_field="cost"),
        "live": live_trade_stats(read_csv(LIVE_FILE)),
        "scalp": scalp_stats(read_csv(SCALP_FILE)),
        "shadow": shadow_stats(read_csv(SHADOW_FILE)),
        "bots": bot_statuses(),
    }


def process_running(process):
    return process is not None and process.poll() is None


def bot_statuses():
    statuses = []

    for bot_id, config in BOTS.items():
        process = BOT_PROCESSES.get(bot_id)
        running = process_running(process)
        statuses.append({
            "id": bot_id,
            "name": config["name"],
            "mode": config["mode"],
            "description": config["description"],
            "running": running,
            "pid": process.pid if running else None,
            "returnCode": None if process is None or running else process.poll(),
            "logFile": str(log_path(bot_id).relative_to(ROOT)),
        })

    return statuses


def log_path(bot_id):
    return LOG_DIR / f"{bot_id}.log"


def dashboard_event(message):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


def start_bot(bot_id):
    if bot_id not in BOTS:
        dashboard_event(f"START failed | unknown bot: {bot_id}")
        return {"error": "unknown bot"}, 404

    process = BOT_PROCESSES.get(bot_id)
    if process_running(process):
        dashboard_event(
            f"START skipped | {BOTS[bot_id]['name']} already running | pid={process.pid}"
        )
        return {"ok": True, "message": "already running", "bot": bot_id}, 200

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    config = BOTS[bot_id]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.update(config.get("env", {}))
    log_file = log_path(bot_id).open("a")
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "src" / config["script"])],
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(STARTUP_CHECK_SECONDS)
    return_code = process.poll()
    if return_code is not None:
        dashboard_event(
            f"START failed | {config['name']} exited immediately | return_code={return_code}"
        )
        return {
            "ok": False,
            "message": "bot exited immediately; check log",
            "bot": bot_id,
            "returnCode": return_code,
            "logFile": str(log_path(bot_id).relative_to(ROOT)),
        }, 409

    BOT_PROCESSES[bot_id] = process
    dashboard_event(
        f"STARTED | {config['name']} | pid={process.pid} | log={log_path(bot_id).relative_to(ROOT)}"
    )
    return {"ok": True, "message": "started", "bot": bot_id, "pid": process.pid}, 200


def stop_process(bot_id, process):
    if not process_running(process):
        return

    dashboard_event(f"STOPPING | {BOTS[bot_id]['name']} | pid={process.pid}")
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        dashboard_event(f"STOP escalation | {BOTS[bot_id]['name']} | sending SIGTERM")
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)

    dashboard_event(
        f"STOPPED | {BOTS[bot_id]['name']} | return_code={process.returncode}"
    )


def stop_bot(bot_id):
    if bot_id not in BOTS:
        dashboard_event(f"STOP failed | unknown bot: {bot_id}")
        return {"error": "unknown bot"}, 404

    process = BOT_PROCESSES.get(bot_id)
    if not process_running(process):
        dashboard_event(f"STOP skipped | {BOTS[bot_id]['name']} is not running")
        return {"ok": True, "message": "not running", "bot": bot_id}, 200

    stop_process(bot_id, process)
    return {"ok": True, "message": "stopped", "bot": bot_id}, 200


def stop_all_bots():
    for bot_id, process in list(BOT_PROCESSES.items()):
        stop_process(bot_id, process)


def json_response(handler, payload, status=200):
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/stats":
            json_response(self, build_payload())
            return

        requested = "index.html" if path == "/" else path.lstrip("/")
        file_path = (DASHBOARD_DIST / requested).resolve()
        if not str(file_path).startswith(str(DASHBOARD_DIST.resolve())):
            self.send_error(403)
            return

        if not file_path.exists() and "." not in requested:
            file_path = DASHBOARD_DIST / "index.html"

        if not file_path.exists():
            json_response(
                self,
                {
                    "error": (
                        "Dashboard build not found. Run "
                        "`cd dashboard && npm install && npm run build`."
                    )
                },
                status=404,
            )
            return

        body = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            body = json.loads(raw_body.decode() or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "invalid json"}, status=400)
            return

        bot_id = body.get("botId")
        if path == "/api/bots/start":
            payload, status = start_bot(bot_id)
            json_response(self, payload, status=status)
            return

        if path == "/api/bots/stop":
            payload, status = stop_bot(bot_id)
            json_response(self, payload, status=status)
            return

        json_response(self, {"error": "unknown endpoint"}, status=404)


def main():
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8765"))

    server = None
    selected_port = port
    for candidate_port in range(port, port + 20):
        try:
            server = HTTPServer((host, candidate_port), DashboardHandler)
            selected_port = candidate_port
            break
        except OSError as exc:
            if exc.errno != 48:
                raise

    if server is None:
        raise RuntimeError(f"No free dashboard port found from {port} to {port + 19}")

    print(f"Dashboard running at http://{host}:{selected_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopping...", flush=True)
        stop_all_bots()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
