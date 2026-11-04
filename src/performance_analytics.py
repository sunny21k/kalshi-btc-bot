from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


REPORTING_TIMEZONE = "America/New_York"


def finite_decimal(value):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def dated_timestamp(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    try:
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def build_performance(rows, *, kind="paper", now=None):
    if kind not in ("paper", "live", "scalp"):
        raise ValueError("Unknown performance kind")
    zone = ZoneInfo(REPORTING_TIMEZONE)
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date()
    records = []
    seen = set()
    pending_keys = set()
    pending = 0
    excluded = {"invalidDate": 0, "invalidProfitLoss": 0, "duplicates": 0}
    if kind == "scalp":
        rows = [row for row in rows if not row.get("error") and row.get("side") in ("YES", "NO")
                and str(row.get("trade_id", "")).startswith("scalp-")]
        opened = {row.get("trade_id") for row in rows if row.get("event") == "OPEN" and not row.get("error")}
        closed = {row.get("trade_id") for row in rows if row.get("event") == "CLOSE" and not row.get("error")}
        pending = len(opened - closed - {None, ""})

    for index, row in enumerate(rows):
        if row.get("error") or row.get("side") not in ("YES", "NO"):
            continue
        if kind == "scalp":
            if row.get("event") != "CLOSE" or not str(row.get("trade_id", "")).startswith("scalp-"):
                continue
        elif kind == "live":
            filled = finite_decimal(row.get("filled_count"))
            if filled is None or filled <= 0:
                continue

        identity = (row.get("order_id") if kind == "live" else None) or row.get("trade_id")
        if identity:
            if identity in seen:
                excluded["duplicates"] += 1
                continue

        if kind != "scalp" and row.get("actual_result") not in ("YES", "NO"):
            pending_keys.add(identity or ("row", index))
            continue
        fees = finite_decimal(row.get("fees_paid")) if kind == "live" else None
        if kind == "live" and (row.get("pnl_basis") != "ACTUAL" or fees is None):
            pending_keys.add(identity or ("row", index))
            continue
        profit = finite_decimal(row.get("profit_loss"))
        if profit is None:
            excluded["invalidProfitLoss"] += 1
            continue
        stamp = dated_timestamp((row.get("closed_at") or row.get("timestamp")) if kind == "scalp" else row.get("timestamp"))
        try:
            report_date = stamp.astimezone(zone).date() if stamp is not None else None
        except (ValueError, OverflowError):
            report_date = None
        if report_date is None or report_date > today:
            excluded["invalidDate"] += 1
            continue
        cost = finite_decimal(row.get("fill_cost") if kind == "live" else row.get("cost"))
        if cost is not None and cost < 0:
            cost = None
        if identity:
            seen.add(identity)
        records.append((stamp, profit, cost, fees))

    if kind != "scalp":
        pending = len(pending_keys - seen)
    by_day = defaultdict(list)
    for stamp, profit, cost, fees in sorted(records, key=lambda item: item[0]):
        by_day[stamp.astimezone(zone).date().isoformat()].append((profit, cost, fees))

    days = []
    cumulative = Decimal("0")
    for date, trades in sorted(by_day.items()):
        net = peak = trough = drawdown = Decimal("0")
        gross_profit = gross_loss = invested = fee_total = Decimal("0")
        profitable = losing = flat = 0
        complete_cost = True
        for profit, cost, fees in trades:
            net += profit
            peak = max(peak, net)
            trough = min(trough, net)
            drawdown = max(drawdown, peak - net)
            if profit > 0:
                profitable += 1
                gross_profit += profit
            elif profit < 0:
                losing += 1
                gross_loss -= profit
            else:
                flat += 1
            if cost is None:
                complete_cost = False
            else:
                invested += cost
            if fees is not None:
                fee_total += fees
        cumulative += net
        days.append({
            "date": date,
            "profitLoss": f"{net:.4f}",
            "cumulative": f"{cumulative:.4f}",
            "trades": len(trades),
            "profitable": profitable,
            "losing": losing,
            "flat": flat,
            "grossProfit": f"{gross_profit:.4f}",
            "grossLoss": f"{gross_loss:.4f}",
            "invested": f"{invested:.4f}" if complete_cost else None,
            "fees": f"{fee_total:.4f}" if kind == "live" else None,
            # Prefix extremes retain intraday drawdown when date ranges change.
            "peak": f"{peak:.4f}",
            "trough": f"{trough:.4f}",
            "drawdown": f"{drawdown:.4f}",
        })

    return {
        "timezone": REPORTING_TIMEZONE,
        "dateBasis": "close" if kind == "scalp" else "entry",
        "kind": kind,
        "today": today.isoformat(),
        "days": days,
        "pending": pending,
        "excluded": excluded,
    }
