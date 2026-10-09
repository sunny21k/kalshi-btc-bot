from dataclasses import dataclass
from decimal import Decimal


MIN_ENTRY_PRICE = Decimal("0.20")
MAX_ENTRY_PRICE = Decimal("0.95")
MAX_SPREAD = Decimal("0.05")


@dataclass
class Candle:
    start_ts: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @property
    def body(self):
        return abs(self.close - self.open)

    @property
    def direction(self):
        if self.close > self.open:
            return "UP"
        if self.close < self.open:
            return "DOWN"
        return "FLAT"


def build_candle(start_ts, prices):
    values = [Decimal(str(price)) for price in prices]
    return Candle(
        start_ts=Decimal(str(start_ts)),
        open=values[0],
        high=max(values),
        low=min(values),
        close=values[-1],
    )


def bodies_are_not_shrinking(candles):
    if len(candles) < 2:
        return False

    return candles[-1].body >= candles[-2].body


def candles_shrinking(candles, *, count=3):
    if len(candles) < count:
        return False

    recent = candles[-count:]
    bodies = [candle.body for candle in recent]
    return all(bodies[index] < bodies[index - 1] for index in range(1, len(bodies)))


def choose_scalp_entry(candles_5s, candles_15s, *, yes_ask, no_ask, spread):
    if len(candles_5s) < 3 or len(candles_15s) < 1:
        return wait("not enough candle history")

    spread = Decimal(str(spread))
    if spread > MAX_SPREAD:
        return wait("spread too wide")

    recent_5s = candles_5s[-3:]
    directions = [candle.direction for candle in recent_5s]
    confirmation_direction = candles_15s[-1].direction

    if directions.count("UP") == 3 and confirmation_direction != "DOWN":
        return entry_if_price_ok(
            side="YES",
            prediction="UP",
            entry_price=yes_ask,
            reason="5s candles up with 15s confirmation",
            candles=recent_5s,
        )

    if directions.count("DOWN") == 3 and confirmation_direction != "UP":
        return entry_if_price_ok(
            side="NO",
            prediction="DOWN",
            entry_price=no_ask,
            reason="5s candles down with 15s confirmation",
            candles=recent_5s,
        )

    return wait("no candle continuation")


def entry_if_price_ok(*, side, prediction, entry_price, reason, candles):
    if not bodies_are_not_shrinking(candles):
        return wait("entry candle body shrinking")

    entry_price = Decimal(str(entry_price))
    if not MIN_ENTRY_PRICE <= entry_price <= MAX_ENTRY_PRICE:
        return wait(f"{side} ask outside scalp price band")

    return {
        "decision": f"BUY {side}",
        "side": side,
        "prediction": prediction,
        "entry_price": entry_price,
        "reason": reason,
    }


def wait(reason):
    return {
        "decision": "WAIT",
        "side": "",
        "prediction": "NEUTRAL",
        "entry_price": None,
        "reason": reason,
    }


def mark_price_for_side(side, yes_bid, no_bid):
    if side == "YES":
        return Decimal(str(yes_bid))
    if side == "NO":
        return Decimal(str(no_bid))
    raise ValueError(f"Unsupported side: {side}")


def current_profit(position, mark_price):
    return (
        Decimal(str(mark_price)) - Decimal(str(position["entry_price"]))
    ) * Decimal(str(position["contracts"]))


def choose_scalp_exit(
    position,
    candles_5s,
    *,
    yes_bid,
    no_bid,
    trailing_activation,
    trailing_floor,
    stop_loss,
):
    mark_price = mark_price_for_side(position["side"], yes_bid, no_bid)
    profit = current_profit(position, mark_price)
    peak_profit = max(Decimal(str(position["peak_profit"])), profit)

    if profit <= -Decimal(str(stop_loss)):
        return exit_signal(mark_price, profit, peak_profit, "stop loss")

    if peak_profit >= Decimal(str(trailing_activation)) and profit <= Decimal(str(trailing_floor)):
        return exit_signal(mark_price, profit, peak_profit, "trailing profit floor")

    if candles_shrinking(candles_5s):
        return exit_signal(mark_price, profit, peak_profit, "candle bodies shrinking")

    return {
        "decision": "HOLD",
        "exit_price": mark_price,
        "current_profit": profit,
        "peak_profit": peak_profit,
        "reason": "hold",
    }


def exit_signal(exit_price, profit, peak_profit, reason):
    return {
        "decision": "SELL",
        "exit_price": Decimal(str(exit_price)),
        "current_profit": Decimal(str(profit)),
        "peak_profit": Decimal(str(peak_profit)),
        "reason": reason,
    }
