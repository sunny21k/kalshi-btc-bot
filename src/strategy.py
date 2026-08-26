from decimal import Decimal


def calculate_btc_change(current_price, previous_price):
    """
    Calculate BTC percentage change from the previous price.
    """

    if previous_price is None or previous_price == 0:
        return Decimal("0")

    current_price = Decimal(str(current_price))
    previous_price = Decimal(str(previous_price))

    return ((current_price - previous_price) / previous_price) * Decimal("100")


def get_signal(price_change):
    """
    Convert BTC price movement into a simple signal.
    """

    price_change = Decimal(str(price_change))

    if price_change > Decimal("0.02"):
        return "UP"

    if price_change < Decimal("-0.02"):
        return "DOWN"

    return "NEUTRAL"


def estimate_probability(signal, price_change):
    """
    Estimate the probability of YES based on BTC movement.

    This is intentionally a simple starting model.
    We will improve this later.
    """

    price_change = Decimal(str(price_change))

    if signal == "UP":
        strength = min(abs(price_change) / Decimal("0.10"), Decimal("1"))
        return Decimal("0.50") + (strength * Decimal("0.20"))

    if signal == "DOWN":
        strength = min(abs(price_change) / Decimal("0.10"), Decimal("1"))
        return Decimal("0.50") - (strength * Decimal("0.20"))

    return Decimal("0.50")


def calculate_edge(model_probability, yes_price_cents):
    """
    Compare our estimated probability against the Kalshi YES price.
    """

    model_probability = Decimal(str(model_probability))
    market_probability = Decimal(str(yes_price_cents)) / Decimal("100")

    return model_probability - market_probability


def make_decision(
    signal,
    model_probability,
    yes_price_cents,
    *,
    minimum_edge=Decimal("0.05"),
):
    """
    Decide whether the bot should BUY YES or WAIT.
    """

    if signal != "UP":
        return "WAIT"

    edge = calculate_edge(
        model_probability,
        yes_price_cents,
    )

    if edge >= minimum_edge:
        return "BUY"

    return "WAIT"