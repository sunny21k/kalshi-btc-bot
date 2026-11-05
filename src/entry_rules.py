"""Serializable entry rules shared by the dashboard, runners, and rule details."""

import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation

from entry_prices import parse_entry_price_range, serialize_entry_price_range

RULES_ENV = 'KALSHI_ENTRY_RULES'
BOT_IDS = ('btc15_paper', 'btc15_dual_paper', 'btc15_direction_paper', 'btc15_live', 'btc15_dual_live', 'scalp_paper')


def numeric(value, label, *, minimum=0, maximum=None):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < minimum or (maximum is not None and number > maximum):
            raise ValueError(f'{label} is outside its allowed range')
        if number != number.quantize(Decimal('.01')):
            raise ValueError(f'{label} allows at most two decimal places')
    except InvalidOperation as exc:
        raise ValueError(f'Enter a valid {label.lower()}') from exc
    return format(number.normalize(), 'f')


def validate_entry_rules(value, bot_id=None):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError('Use a list of at most 20 entry rules')
    result, seen = [], set()
    keys = {'id', 'name', 'enabled', 'maxMinutesLeft', 'minBtcDistance', 'side', 'priceRange', 'requireDirection'}
    for index, rule in enumerate(value, 1):
        if not isinstance(rule, dict) or set(rule) != keys:
            raise ValueError(f'Rule {index} has missing or unsupported fields')
        rule_id = rule['id']
        if not isinstance(rule_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', rule_id) or rule_id in seen:
            raise ValueError('Every rule needs a unique valid ID')
        seen.add(rule_id)
        if not isinstance(rule['name'], str) or not 1 <= len(rule['name'].strip()) <= 60 or any(ord(c) < 32 for c in rule['name']):
            raise ValueError(f'Rule {index} needs a name of 1–60 characters')
        if type(rule['enabled']) is not bool or type(rule['requireDirection']) is not bool:
            raise ValueError('Rule switches must be true or false')
        if rule['side'] not in ('BOTH', 'YES', 'NO') or (bot_id == 'btc15_paper' and rule['side'] == 'YES'):
            raise ValueError('Choose an allowed side for this bot')
        minutes = numeric(rule['maxMinutesLeft'], 'Minutes remaining', minimum=Decimal('.01'), maximum=15)
        distance = numeric(rule['minBtcDistance'], 'BTC distance', maximum=10000000)
        band = serialize_entry_price_range(rule['priceRange'])
        if band is None:
            raise ValueError('Every rule needs its own entry price range')
        result.append({**rule, 'name': rule['name'].strip(), 'maxMinutesLeft': minutes, 'minBtcDistance': distance, 'priceRange': band})
    return result


def default_entry_rules(bot_id):
    if bot_id not in BOT_IDS:
        raise ValueError('Unknown bot')
    if bot_id == 'scalp_paper':
        return []
    import strategy
    def rule(rule_id, name, seconds, distance, low, high, side='BOTH', direction=False):
        return dict(id=rule_id, name=name, enabled=True, maxMinutesLeft=str(seconds / 60),
                    minBtcDistance=str(distance), side=side, priceRange={'min': str(low), 'max': str(high)}, requireDirection=direction)
    side = 'NO' if bot_id == 'btc15_paper' else 'BOTH'
    rules = []
    if bot_id == 'btc15_live':
        rules.append(rule('early_up_9m_70', 'Early YES', strategy.MAX_EARLY_UP_ENTRY_SECONDS,
                          strategy.MIN_EARLY_UP_PRICE_DIFFERENCE, strategy.MIN_LATE_ENTRY_PRICE, strategy.MAX_STRONG_RULE_ENTRY_PRICE, side='YES'))
    rules.extend([
        rule('strong_5m_50', 'Strong entry', strategy.MAX_STRONG_ENTRY_SECONDS, strategy.MIN_STRONG_BTC_PRICE_DIFFERENCE,
             strategy.MIN_DUAL_LIVE_STRONG_ENTRY_PRICE if bot_id == 'btc15_dual_live' else strategy.MIN_LATE_ENTRY_PRICE,
             strategy.MAX_STRONG_RULE_ENTRY_PRICE, side=side, direction=bot_id == 'btc15_direction_paper'),
        rule('late_4m_10', 'Late entry', strategy.MAX_LATE_ENTRY_SECONDS, strategy.MIN_BTC_PRICE_DIFFERENCE,
             strategy.MIN_LATE_ENTRY_PRICE, strategy.MAX_LATE_RULE_ENTRY_PRICE, side=side),
    ])
    return validate_entry_rules(rules, bot_id)


def entry_rules_from_env(bot_id):
    value = os.getenv(RULES_ENV, '').strip()
    if not value:
        return None
    try:
        return validate_entry_rules(json.loads(value), bot_id)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Invalid saved entry rules: {exc}') from exc


def matching_entry_rule(rules, *, price_difference, seconds_remaining, side):
    if seconds_remaining is None or price_difference is None or side not in ('YES', 'NO'):
        return None
    return next((rule for rule in rules if rule['enabled'] and rule['side'] in ('BOTH', side)
                 and Decimal(str(seconds_remaining)) <= Decimal(rule['maxMinutesLeft']) * 60
                 and abs(Decimal(str(price_difference))) >= Decimal(rule['minBtcDistance'])), None)


def strategy_name(rule):
    for bot_id in BOT_IDS:
        if rule in default_entry_rules(bot_id):
            return rule['id'] + ('_direction' if rule['requireDirection'] else '')
    digest = hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()[:6]
    name = re.sub(r'[^a-zA-Z0-9]+', '_', rule['name']).strip('_') or 'rule'
    return f"{name}_{rule['maxMinutesLeft']}m_{rule['minBtcDistance']}_{digest}"


def evaluate_entry_rules(*, entry_rules, btc_price, target_price, seconds_remaining, yes_ask, no_ask,
                         spread=None, recent_prices=None, previous_entry_price=None, confirmation_count=0,
                         rule_confirmation_counts=None, entry_price_range=None):
    from strategy import MIN_SECONDS_TO_CLOSE, MAX_ENTRY_SPREAD, MIN_CONFIRMATION_POLLS, MAX_ASK_CHASE_MOVE, momentum_confirms, has_wild_reversal
    from direction_strategy import consecutive_direction_matches
    result = dict(decision='WAIT', side='', prediction='NEUTRAL', entry_price=None, price_difference=None)
    def wait(reason):
        return {**result, 'reason': reason}
    rules = validate_entry_rules(entry_rules)
    if not any(rule['enabled'] for rule in rules):
        return wait('No enabled entry rules')
    if target_price in (None, ''):
        return wait('target price unavailable')
    if seconds_remaining is None:
        return wait('time remaining unavailable')
    if Decimal(str(seconds_remaining)) <= MIN_SECONDS_TO_CLOSE:
        return wait('inside final 30 seconds')
    if spread is not None and Decimal(str(spread)) > MAX_ENTRY_SPREAD:
        return wait('spread wider than 3 cents')
    difference = Decimal(str(btc_price)) - Decimal(str(target_price))
    result['price_difference'] = difference
    if not difference:
        return wait('BTC equals target')
    side = 'YES' if difference > 0 else 'NO'
    rule = matching_entry_rule(rules, price_difference=difference, seconds_remaining=seconds_remaining, side=side)
    if not rule:
        return wait('No entry rule matches the time, BTC distance, and side')
    price = yes_ask if side == 'YES' else no_ask
    result.update(side=side, prediction='UP' if side == 'YES' else 'DOWN', entry_price=price,
                  strategy_name=strategy_name(rule), entry_rule=rule)
    count = (rule_confirmation_counts or {}).get((rule['id'], side), 0) if rule_confirmation_counts is not None else confirmation_count
    if count < MIN_CONFIRMATION_POLLS:
        return wait(f"{rule['name']}: distance not confirmed for {MIN_CONFIRMATION_POLLS} polls")
    if not momentum_confirms(result['prediction'], recent_prices):
        return wait(f"recent BTC momentum does not confirm {result['prediction']}")
    if has_wild_reversal(result['prediction'], recent_prices):
        return wait('recent BTC reversal too large')
    if rule['requireDirection'] and not consecutive_direction_matches(side, recent_prices):
        return wait(f'need 3 consecutive BTC moves for {side}')
    if price is None:
        return wait(f'{side} ask unavailable')
    price = Decimal(str(price))
    band = parse_entry_price_range(entry_price_range or rule['priceRange'])
    if not band['min'] <= price <= band['max']:
        return wait(f"{rule['name']}: {side} ask outside allowed price band")
    if previous_entry_price is not None and price - Decimal(str(previous_entry_price)) > MAX_ASK_CHASE_MOVE:
        return wait('ask moved up too fast')
    return {**result, 'entry_price': price, 'decision': f'BUY {side}', 'reason': f"{rule['name']} rule passed"}


def filter_scalp_entry(entry, rules, *, btc_price, target_price, seconds_remaining, recent_prices, entry_price_range=None):
    if not rules or entry['decision'] not in ('BUY YES', 'BUY NO'):
        return entry
    from direction_strategy import consecutive_direction_matches
    difference = None if target_price in (None, '') else Decimal(str(btc_price)) - Decimal(str(target_price))
    rule = matching_entry_rule(rules, price_difference=difference, seconds_remaining=seconds_remaining, side=entry['side'])
    reason = 'No scalp entry filter matches the time, BTC distance, and side'
    if rule:
        band = parse_entry_price_range(entry_price_range or rule['priceRange'])
        if not band['min'] <= entry['entry_price'] <= band['max']:
            reason = f"{rule['name']}: ask outside allowed price band"
        elif rule['requireDirection'] and not consecutive_direction_matches(entry['side'], recent_prices):
            reason = f"{rule['name']}: need 3 matching BTC moves"
        else:
            return {**entry, 'reason': f"{entry['reason']}; {rule['name']}", 'entry_rule': rule}
    return {**entry, 'decision': 'WAIT', 'reason': reason}
