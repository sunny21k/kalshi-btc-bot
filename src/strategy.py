from collections import deque


prices = deque(maxlen=60)


def add_price(price):
    prices.append(price)


def get_signal():
    if len(prices) < 10:
        return "WAIT"

    old_price = prices[0]
    current_price = prices[-1]

    change = (current_price - old_price) / old_price

    if change > 0.0002:
        return "UP"

    if change < -0.0002:
        return "DOWN"

    return "NEUTRAL"