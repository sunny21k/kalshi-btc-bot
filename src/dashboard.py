import csv
import json
import mimetypes
import os
from collections import Counter, defaultdict
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DASHBOARD_DIST = ROOT / "dashboard" / "dist"
PAPER_FILE = DATA_DIR / "paper_trades.csv"
LIVE_FILE = DATA_DIR / "live_trades.csv"
SHADOW_FILE = DATA_DIR / "shadow_signals.csv"


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


def shadow_stats(rows):
    reasons = Counter(row.get("reason") or "unknown" for row in rows)
    decisions = Counter(row.get("decision") or "unknown" for row in rows)
    return {
        "total": len(rows),
        "decisions": dict(decisions.most_common(12)),
        "blockedReasons": dict(reasons.most_common(12)),
        "recent": rows[-30:][::-1],
    }


def build_payload():
    return {
        "paper": trade_stats(read_csv(PAPER_FILE), cost_field="cost"),
        "live": trade_stats(read_csv(LIVE_FILE), cost_field="max_cost"),
        "shadow": shadow_stats(read_csv(SHADOW_FILE)),
    }


def json_response(handler, payload, status=200):
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class DashboardHandler(BaseHTTPRequestHandler):
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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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
    server.serve_forever()


if __name__ == "__main__":
    main()
