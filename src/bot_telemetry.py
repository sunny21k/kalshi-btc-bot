"""Local, best-effort bot observations. These never decide or place trades."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


STATUS_DIR = Path(__file__).resolve().parents[1] / "data" / "bot_status"
BOT_IDS = {"btc15_paper", "btc15_dual_paper", "btc15_live", "btc15_dual_live", "scalp_paper"}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class BotTelemetry:
    def __init__(self, bot_id, *, poll_seconds=5, settings=None):
        if bot_id not in BOT_IDS:
            raise ValueError("Unknown bot telemetry ID")
        self.path = STATUS_DIR / f"{bot_id}.json"
        self.data = {
            "botId": bot_id, "pid": os.getpid(), "startedAt": timestamp(),
            "stoppedAt": None, "heartbeatAt": None,
            "staleAfterSeconds": max(45, float(poll_seconds) * 5),
            "stage": "Starting", "price": None, "market": {},
            "decision": None, "lastError": None, "lastApiError": None,
            "settings": settings or {},
        }
        self.save()

    def save(self):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as file:
                temporary = file.name
                json.dump(self.data, file, default=str, allow_nan=False)
            os.replace(temporary, self.path)
        except (OSError, TypeError, ValueError):
            # An unavailable diagnostics disk must never change execution behavior.
            pass
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

    def stage(self, name):
        self.data.update(stage=name, heartbeatAt=timestamp())
        self.save()

    def recovered(self, source):
        for field in ("lastError", "lastApiError"):
            error = self.data[field]
            if error and error["source"] == source and error["active"]:
                error.update(active=False, recoveredAt=timestamp())

    def price(self, value):
        self.data["price"] = {"value": str(value), "at": timestamp()}
        self.recovered("BTC feed")
        self.save()

    def market(self, **values):
        self.data["market"] = {**values, "at": timestamp()}
        self.recovered("Kalshi")
        self.save()

    def decide(self, action, reason, *, side="", strategy=""):
        self.data["decision"] = {
            "action": action, "reason": reason, "side": side,
            "strategy": strategy, "at": timestamp(),
        }
        if self.data["lastError"] and self.data["lastError"]["source"] not in ("Kalshi", "BTC feed"):
            self.data["lastError"].update(active=False, recoveredAt=timestamp())
        self.data.update(heartbeatAt=timestamp(), stage="Watching market")
        self.save()

    def failure(self, error, *, source, api=False):
        detail = {
            "message": str(error)[:600], "type": type(error).__name__,
            "source": source, "at": timestamp(), "active": True, "recoveredAt": None,
        }
        self.data["lastError"] = detail.copy()
        if api:
            self.data["lastApiError"] = detail.copy()
        self.data["decision"] = {"action": "ERROR", "reason": detail["message"], "at": timestamp()}
        self.data.update(heartbeatAt=timestamp(), stage=f"Retrying after {source} error")
        self.save()

    def stop(self):
        self.data.update(stoppedAt=timestamp(), heartbeatAt=timestamp(), stage="Stopped")
        self.save()


def read_snapshot(bot_id):
    if bot_id not in BOT_IDS:
        return None
    try:
        with (STATUS_DIR / f"{bot_id}.json").open() as file:
            data = json.load(file)
        if not isinstance(data, dict) or data.get("botId") != bot_id:
            return None
        for key in ("price", "market", "decision", "lastError", "lastApiError", "settings"):
            if data.get(key) is not None and not isinstance(data[key], dict):
                return None
        return data
    except (OSError, ValueError):
        return None


def age_seconds(value, now):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            return None
        age = (now - date).total_seconds()
        return round(max(0, age), 1) if age >= -2 else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def process_alive(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False


def runtime_status(bot_id, *, running=False, pid=None, managed=False, now=None):
    now = now or datetime.now(timezone.utc)
    data = read_snapshot(bot_id)
    if managed and (not data or data.get("pid") != pid):
        data = None
    data = data or {}
    age = age_seconds(data.get("heartbeatAt"), now)
    price = data.get("price") or {}
    price_age = age_seconds(price.get("at"), now)
    alive = running if managed else bool(not data.get("stoppedAt") and process_alive(data.get("pid")))
    stale_after = data.get("staleAfterSeconds", 45)
    if not isinstance(stale_after, (int, float)) or not 10 <= stale_after <= 600:
        stale_after = 45
    error = data.get("lastError") or {}
    if not alive:
        state = "stopped"
    elif age is None:
        state = "starting"
    elif age > stale_after or (price_age is not None and price_age > stale_after):
        state = "stale"
    elif not price and not error.get("active"):
        state = "starting"
    elif error.get("active"):
        state = "degraded"
    else:
        state = "healthy"
    return {
        **data, "state": state, "processAlive": alive, "managed": managed,
        "heartbeatAgeSeconds": age, "priceAgeSeconds": price_age,
        "staleAfterSeconds": stale_after, "blockers": [],
    }
