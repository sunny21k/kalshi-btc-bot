from decimal import Decimal


MIN_LATE_ENTRY_PRICE = Decimal("0.75")
MAX_LATE_ENTRY_PRICE = Decimal("0.92")
MAX_LATE_ENTRY_SECONDS = Decimal("240")
MIN_BTC_PRICE_DIFFERENCE = Decimal("10")
MAX_STRONG_ENTRY_SECONDS = Decimal("300")
MIN_STRONG_BTC_PRICE_DIFFERENCE = Decimal("50")
MAX_EARLY_UP_ENTRY_SECONDS = Decimal("540")
MIN_EARLY_UP_PRICE_DIFFERENCE = Decimal("70")
MIN_SECONDS_TO_CLOSE = Decimal("30")
MAX_ENTRY_SPREAD = Decimal("0.03")
MAX_LATE_RULE_ENTRY_PRICE = Decimal("0.85")
MAX_STRONG_RULE_ENTRY_PRICE = Decimal("0.92")
MAX_ASK_CHASE_MOVE = Decimal("0.05")
MIN_CONFIRMATION_POLLS = 3
MAX_REVERSAL_DOLLARS = Decimal("10")


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
    *,
    spread=None,
    recent_prices=None,
    previous_entry_price=None,
    confirmation_count=0,
    enable_early_up=True,
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
    if seconds_remaining <= MIN_SECONDS_TO_CLOSE:
        return {
            "decision": "WAIT",
            "side": "",
            "prediction": "NEUTRAL",
            "entry_price": None,
            "price_difference": None,
            "reason": "inside final 30 seconds",
        }

    if spread is not None and Decimal(str(spread)) > MAX_ENTRY_SPREAD:
        return {
            "decision": "WAIT",
            "side": "",
            "prediction": "NEUTRAL",
            "entry_price": None,
            "price_difference": None,
            "reason": "spread wider than 3 cents",
        }

    btc_price = Decimal(str(btc_price))
    target_price = Decimal(str(target_price))
    price_difference = btc_price - target_price

    early_up_rule_passed = (
        enable_early_up
        and seconds_remaining <= MAX_EARLY_UP_ENTRY_SECONDS
        and price_difference >= MIN_EARLY_UP_PRICE_DIFFERENCE
    )
    strong_rule_passed = (
        seconds_remaining <= MAX_STRONG_ENTRY_SECONDS
        and abs(price_difference) >= MIN_STRONG_BTC_PRICE_DIFFERENCE
    )
    late_rule_passed = (
        seconds_remaining <= MAX_LATE_ENTRY_SECONDS
        and abs(price_difference) >= MIN_BTC_PRICE_DIFFERENCE
    )

    if not early_up_rule_passed and not strong_rule_passed and not late_rule_passed:
        if not enable_early_up and seconds_remaining > MAX_STRONG_ENTRY_SECONDS:
            reason = "more than 5 minutes left"
        elif seconds_remaining > MAX_EARLY_UP_ENTRY_SECONDS:
            reason = "more than 9 minutes left"
        elif price_difference >= 0 and seconds_remaining > MAX_STRONG_ENTRY_SECONDS:
            reason = "BTC is less than $70 above target"
        elif seconds_remaining > MAX_STRONG_ENTRY_SECONDS:
            reason = "more than 5 minutes left"
        elif seconds_remaining > MAX_LATE_ENTRY_SECONDS:
            reason = "BTC is less than $50 from target"
        else:
            reason = "BTC is less than $10 from target"

        return {
            "decision": "WAIT",
            "side": "",
            "prediction": "NEUTRAL",
            "entry_price": None,
            "price_difference": price_difference,
            "reason": reason,
        }

    if price_difference >= MIN_BTC_PRICE_DIFFERENCE:
        side = "YES"
        prediction = "UP"
        entry_price = yes_ask
    else:
        side = "NO"
        prediction = "DOWN"
        entry_price = no_ask

    strategy_name = (
        "early_up_9m_70"
        if early_up_rule_passed
        else (
            "strong_5m_50"
            if strong_rule_passed
            else "late_4m_10"
        )
    )

    if confirmation_count < MIN_CONFIRMATION_POLLS:
        return {
            "decision": "WAIT",
            "side": side,
            "prediction": prediction,
            "entry_price": entry_price,
            "price_difference": price_difference,
            "strategy_name": strategy_name,
            "reason": "price threshold not confirmed for 3 polls",
        }

    if not momentum_confirms(prediction, recent_prices):
        return {
            "decision": "WAIT",
            "side": side,
            "prediction": prediction,
            "entry_price": entry_price,
            "price_difference": price_difference,
            "strategy_name": strategy_name,
            "reason": f"recent BTC momentum does not confirm {prediction}",
        }

    if has_wild_reversal(prediction, recent_prices):
        return {
            "decision": "WAIT",
            "side": side,
            "prediction": prediction,
            "entry_price": entry_price,
            "price_difference": price_difference,
            "strategy_name": strategy_name,
            "reason": "recent BTC reversal too large",
        }

    if entry_price is None:
        return {
            "decision": "WAIT",
            "side": side,
            "prediction": prediction,
            "entry_price": None,
            "price_difference": price_difference,
            "strategy_name": strategy_name,
            "reason": f"{side} ask unavailable",
        }

    entry_price = Decimal(str(entry_price))
    max_entry_price = (
        MAX_STRONG_RULE_ENTRY_PRICE
        if early_up_rule_passed or strong_rule_passed
        else MAX_LATE_RULE_ENTRY_PRICE
    )
    if not MIN_LATE_ENTRY_PRICE <= entry_price <= max_entry_price:
        return {
            "decision": "WAIT",
            "side": side,
            "prediction": prediction,
            "entry_price": entry_price,
            "price_difference": price_difference,
            "strategy_name": strategy_name,
            "reason": f"{side} ask outside allowed price band",
        }

    if previous_entry_price is not None:
        previous_entry_price = Decimal(str(previous_entry_price))
        if entry_price - previous_entry_price > MAX_ASK_CHASE_MOVE:
            return {
                "decision": "WAIT",
                "side": side,
                "prediction": prediction,
                "entry_price": entry_price,
                "price_difference": price_difference,
                "strategy_name": strategy_name,
                "reason": "ask moved up too fast",
            }

    return {
        "decision": f"BUY {side}",
        "side": side,
        "prediction": prediction,
        "entry_price": entry_price,
        "price_difference": price_difference,
        "strategy_name": strategy_name,
        "reason": (
            "early 9-minute $70 up rule passed"
            if early_up_rule_passed
            else (
                "strong 5-minute $50 rule passed"
                if strong_rule_passed
                else "late 4-minute $10 rule passed"
            )
        ),
    }


def momentum_confirms(prediction, recent_prices):
    if recent_prices is None:
        return True

    prices = [Decimal(str(price)) for price in recent_prices]
    if len(prices) < 3:
        return False

    if prediction == "UP":
        return prices[-1] > prices[0] and prices[-1] >= prices[-2]

    if prediction == "DOWN":
        return prices[-1] < prices[0] and prices[-1] <= prices[-2]

    return False


def has_wild_reversal(prediction, recent_prices):
    if recent_prices is None:
        return False

    prices = [Decimal(str(price)) for price in recent_prices]
    if len(prices) < 4:
        return False

    if prediction == "UP":
        return max(prices) - prices[-1] >= MAX_REVERSAL_DOLLARS

    if prediction == "DOWN":
        return prices[-1] - min(prices) >= MAX_REVERSAL_DOLLARS

    return False
