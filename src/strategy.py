from decimal import Decimal


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
    price_change = Decimal(str(price_change))

    if signal == "UP":
        probability = (
            Decimal("0.50")
            + abs(price_change) * Decimal("2")
        )

        return min(probability, Decimal("0.95"))

    if signal == "DOWN":
        probability = (
            Decimal("0.50")
            - abs(price_change) * Decimal("2")
        )

        return max(probability, Decimal("0.05"))

    return Decimal("0.50")


def calculate_edge(model_probability, market_price):
    market_price = Decimal(str(market_price))

    market_probability = market_price / Decimal("100")

    return model_probability - market_probability


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

        no_probability = Decimal("1") - model_probability

        edge = calculate_edge(
            no_probability,
            no_ask,
        )

        if edge >= Decimal("0.05"):
            return "BUY NO"

        return "WAIT"

    return "WAIT"
