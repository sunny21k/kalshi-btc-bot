from decimal import Decimal


MIN_LATE_ENTRY_PRICE = Decimal("0.75")
MAX_LATE_ENTRY_PRICE = Decimal("0.92")
MAX_LATE_ENTRY_SECONDS = Decimal("240")
MIN_BTC_PRICE_DIFFERENCE = Decimal("10")


def calculate_btc_change(current_price, previous_price):
    if previous_price == 0:
        return Decimal("0")

    return (
        (current_price - previous_price)
        / previous_price
        * Decimal("100")
    )


def get_signal(price_change):
    price_change = Decimal(str(price_change))

    if price_change >= Decimal("0.02"):
        return "UP"

    if price_change <= Decimal("-0.02"):
        return "DOWN"

    return "NEUTRAL"


def estimate_probability(signal, price_change):
    """
    Return the model probability for the predicted side.

    UP means probability of YES.
    DOWN means probability of NO.
    NEUTRAL means no directional edge.
    """
    price_change = Decimal(str(price_change))

    if signal in ["UP", "DOWN"]:
        probability = (
            Decimal("0.50")
            + abs(price_change) * Decimal("2")
        )

        return min(probability, Decimal("0.95"))

    return Decimal("0.50")


def calculate_edge(model_probability, market_price):
    model_probability = Decimal(str(model_probability))
    market_price = Decimal(str(market_price))

    return model_probability - market_price


def make_decision(
    signal,
    model_probability,
    yes_ask,
    no_ask=None,
):
    """
    Decide which side of the market to paper trade.

    UP:
        Evaluate YES.

    DOWN:
        Evaluate NO.

    NEUTRAL:
        WAIT.
    """

    if signal == "UP":

        edge = calculate_edge(
            model_probability,
            yes_ask,
        )

        if edge >= Decimal("0.05"):
            return "BUY YES"

        return "WAIT"

    if signal == "DOWN":

        if no_ask is None:
            return "WAIT"

        edge = calculate_edge(
            model_probability,
            no_ask,
        )

        if edge >= Decimal("0.05"):
            return "BUY NO"

        return "WAIT"

    return "WAIT"


def make_late_momentum_decision(
    btc_price,
    target_price,
    seconds_remaining,
    yes_ask,
    no_ask,
):
    if target_price in (None, ""):
        return {
            "decision": "WAIT",
            "side": "",
            "prediction": "NEUTRAL",
            "entry_price": None,
            "price_difference": None,
            "reason": "target price unavailable",
        }

    if seconds_remaining is None:
        return {
            "decision": "WAIT",
            "side": "",
            "prediction": "NEUTRAL",
            "entry_price": None,
            "price_difference": None,
            "reason": "time remaining unavailable",
        }

    seconds_remaining = Decimal(str(seconds_remaining))
    if seconds_remaining > MAX_LATE_ENTRY_SECONDS:
        return {
            "decision": "WAIT",
            "side": "",
            "prediction": "NEUTRAL",
            "entry_price": None,
            "price_difference": None,
            "reason": "more than 4 minutes left",
        }

    btc_price = Decimal(str(btc_price))
    target_price = Decimal(str(target_price))
    price_difference = btc_price - target_price

    if abs(price_difference) < MIN_BTC_PRICE_DIFFERENCE:
        return {
            "decision": "WAIT",
            "side": "",
            "prediction": "NEUTRAL",
            "entry_price": None,
            "price_difference": price_difference,
            "reason": "BTC is less than $10 from target",
        }

    if price_difference >= MIN_BTC_PRICE_DIFFERENCE:
        side = "YES"
        prediction = "UP"
        entry_price = yes_ask
    else:
        side = "NO"
        prediction = "DOWN"
        entry_price = no_ask

    if entry_price is None:
        return {
            "decision": "WAIT",
            "side": side,
            "prediction": prediction,
            "entry_price": None,
            "price_difference": price_difference,
            "reason": f"{side} ask unavailable",
        }

    entry_price = Decimal(str(entry_price))
    if not MIN_LATE_ENTRY_PRICE <= entry_price <= MAX_LATE_ENTRY_PRICE:
        return {
            "decision": "WAIT",
            "side": side,
            "prediction": prediction,
            "entry_price": entry_price,
            "price_difference": price_difference,
            "reason": f"{side} ask outside 75%-92%",
        }

    return {
        "decision": f"BUY {side}",
        "side": side,
        "prediction": prediction,
        "entry_price": entry_price,
        "price_difference": price_difference,
        "reason": "late momentum rule passed",
    }
