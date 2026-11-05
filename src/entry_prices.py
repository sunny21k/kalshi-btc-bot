"""Validated optional entry-price overrides, in dollar/probability units."""

import os
from decimal import Decimal, InvalidOperation


MIN_ENV = 'KALSHI_MIN_ENTRY_PRICE'
MAX_ENV = 'KALSHI_MAX_ENTRY_PRICE'


def parse_entry_price_range(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'min', 'max'}:
        raise ValueError('Entry price range needs a minimum and maximum')
    try:
        low, high = (Decimal(str(value[key])) for key in ('min', 'max'))
        if not all(price.is_finite() and 0 < price < 1 for price in (low, high)):
            raise ValueError('Entry prices must be greater than 0% and less than 100%')
        if any(price != price.quantize(Decimal('0.0001')) for price in (low, high)):
            raise ValueError('Entry percentages allow at most two decimal places')
    except InvalidOperation as exc:
        raise ValueError('Enter valid minimum and maximum entry prices') from exc
    if low > high:
        raise ValueError('Minimum entry price cannot exceed the maximum')
    return {'min': low, 'max': high}


def entry_price_range_from_env():
    low, high = os.getenv(MIN_ENV, '').strip(), os.getenv(MAX_ENV, '').strip()
    return parse_entry_price_range({'min': low, 'max': high}) if low or high else None


def serialize_entry_price_range(value):
    parsed = parse_entry_price_range(value)
    return {key: f'{price:.4f}' for key, price in parsed.items()} if parsed else None


def default_entry_price_bands(bot_id):
    if bot_id == 'scalp_paper':
        from scalp_strategy import MIN_ENTRY_PRICE, MAX_ENTRY_PRICE
        return [{'label': 'Scalp', 'min': str(MIN_ENTRY_PRICE), 'max': str(MAX_ENTRY_PRICE)}]
    import strategy
    bands = [
        {'label': '4m', 'min': str(strategy.MIN_LATE_ENTRY_PRICE), 'max': str(strategy.MAX_LATE_RULE_ENTRY_PRICE)},
        {'label': '5m', 'min': str(strategy.MIN_DUAL_LIVE_STRONG_ENTRY_PRICE if bot_id == 'btc15_dual_live' else strategy.MIN_LATE_ENTRY_PRICE), 'max': str(strategy.MAX_STRONG_RULE_ENTRY_PRICE)},
    ]
    if bot_id == 'btc15_live':
        bands.append({'label': '9m YES', 'min': str(strategy.MIN_LATE_ENTRY_PRICE), 'max': str(strategy.MAX_STRONG_RULE_ENTRY_PRICE)})
    return bands
