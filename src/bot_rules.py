"""Read-only descriptions built from the strategy constants used by each runner."""

import hashlib
import json
from decimal import Decimal
from entry_prices import parse_entry_price_range
from entry_rules import validate_entry_rules


def amount(value):
    value = Decimal(str(value))
    return format(value, 'f').rstrip('0').rstrip('.') if value % 1 else str(int(value))


def dollars(value):
    value = Decimal(str(value))
    return f'${value:,.2f}' if value == value.quantize(Decimal('0.01')) else f'${value:f}'


def row(label, detail):
    return {'label': label, 'detail': detail}


def section(title, *items):
    return {'title': title, 'items': list(items)}


def build_bot_rules(bot_id, *, settings=None, poll_seconds=None):
    # Imports are delayed until runners have loaded their environment/settings.
    settings = settings or {}
    if bot_id == 'scalp_paper':
        sections = scalp_rules(settings.get('scalp'), entry_price_range=settings.get('entryPriceRange'), entry_rules=settings.get('entryRules'))
        mode = 'paper'
    else:
        sections = fifteen_minute_rules(bot_id, settings, poll_seconds)
        mode = 'live' if bot_id in ('btc15_live', 'btc15_dual_live') else 'paper'
    profile = {'schemaVersion': 1, 'botId': bot_id, 'mode': mode, 'sections': sections}
    profile['fingerprint'] = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    return profile


def fifteen_minute_rules(bot_id, settings, poll_seconds):
    import strategy as rules
    from live_execution import DEFAULT_LIVE_TRADE_BUDGET, MAX_LIVE_TRADES_PER_DAY
    from paper_execution import PAPER_TRADE_BUDGET
    from bot import POLL_SECONDS

    if bot_id not in ('btc15_paper', 'btc15_dual_paper', 'btc15_direction_paper', 'btc15_live', 'btc15_dual_live'):
        raise ValueError('Unknown bot rule profile')
    live = bot_id in ('btc15_live', 'btc15_dual_live')
    no_only = bot_id == 'btc15_paper'
    direction = bot_id == 'btc15_direction_paper'
    early_up = bot_id == 'btc15_live'
    strong_min = rules.MIN_DUAL_LIVE_STRONG_ENTRY_PRICE if bot_id == 'btc15_dual_live' else rules.MIN_LATE_ENTRY_PRICE
    custom = parse_entry_price_range(settings.get('entryPriceRange'))
    late_min, late_max = (custom['min'], custom['max']) if custom else (rules.MIN_LATE_ENTRY_PRICE, rules.MAX_LATE_RULE_ENTRY_PRICE)
    early_min, strong_max = (custom['min'], custom['max']) if custom else (rules.MIN_LATE_ENTRY_PRICE, rules.MAX_STRONG_RULE_ENTRY_PRICE)
    if custom:
        strong_min = custom['min']
    cents = lambda price: f'{amount(price * 100)}¢'
    band = lambda low, high: f'{cents(low)}–{cents(high)} inclusive'
    sides = 'NO only, when BTC is below the target.' if no_only else 'YES above the BTC target; NO below it.'
    entries = []
    if early_up:
        entries.append(row('Early YES entry', f'At most {amount(rules.MAX_EARLY_UP_ENTRY_SECONDS / 60)} minutes left and BTC at least {dollars(rules.MIN_EARLY_UP_PRICE_DIFFERENCE)} above target. YES ask: {band(early_min, strong_max)}.'))
    entries.extend([
        row('5-minute rule', f'At most {amount(rules.MAX_STRONG_ENTRY_SECONDS / 60)} minutes left and BTC at least {dollars(rules.MIN_STRONG_BTC_PRICE_DIFFERENCE)} from target. Ask for the purchased side: {band(strong_min, strong_max)}.'),
        row('4-minute rule', f'At most {amount(rules.MAX_LATE_ENTRY_SECONDS / 60)} minutes left and BTC at least {dollars(rules.MIN_BTC_PRICE_DIFFERENCE)} from target. Ask for the purchased side: {band(late_min, late_max)}.'),
        row('Rule priority', ('Early YES first, then the 5-minute rule, then the 4-minute rule.' if early_up else 'The 5-minute rule takes priority over the 4-minute rule.') + ' If the selected rule fails a price or momentum check, it does not fall back to a lower-priority rule.'),
    ])
    if custom:
        entries.append(row('Custom entry range', 'The selected minimum and maximum replace the price bands for every entry rule. Other strategy checks still apply.'))
    configured = validate_entry_rules(settings.get('entryRules'), bot_id)
    if configured is not None:
        entries = configured_rule_descriptions(configured, override=custom)
    filters = [
        row('Market data', 'Needs an active BTC 15-minute market, its target price, and usable Kalshi order-book quotes. BTC movement uses Coinbase BTC-USD ticks, sampled separately from contract prices.'),
        row('Close cutoff', f'No entry with {amount(rules.MIN_SECONDS_TO_CLOSE)} seconds or less remaining.'),
        row('Spread', f'At most {cents(rules.MAX_ENTRY_SPREAD)} between the quoted bid and ask.'),
        row('Threshold confirmations', f'Requires {rules.MIN_CONFIRMATION_POLLS} recorded polls with BTC at least {dollars(rules.MIN_BTC_PRICE_DIFFERENCE)} from target on the selected side. The counter resets inside that distance. The strong rule checks its larger distance separately on the current poll.'),
        row('BTC momentum', 'Needs at least 3 samples. Across the latest 3–4 BTC prices, the net movement must match the bought side, and the newest move must agree or be flat. YES uses rising BTC; NO uses falling BTC.'),
        row('Reversal filter', f'With 4 samples, rejects YES if BTC has fallen {dollars(rules.MAX_REVERSAL_DOLLARS)} or more from the window high; rejects NO if BTC has risen that much from the window low.'),
        row('Ask chase', f'Rejects an entry if its ask has increased by more than {cents(rules.MAX_ASK_CHASE_MOVE)} since the previous evaluated ask for that market and side.'),
    ]
    if configured is not None:
        filters[3] = row('Threshold confirmations', f'Each rule needs {rules.MIN_CONFIRMATION_POLLS} consecutive polls at its own BTC-distance threshold on the matching side. A side switch or a move inside that rule’s threshold resets its counter.')
        filters.append(row('Direction check', 'Rules with the direction switch enabled also require 3 strictly matching BTC moves across the latest 4 samples. Flat or opposite moves block that rule.'))
    elif direction:
        filters.append(row('Extra direction check', 'For the 5-minute rule, all 3 changes across the latest 4 BTC samples must match the buy: strictly rising for YES or strictly falling for NO. Flat or opposite moves block this rule. The 4-minute rule keeps the normal momentum check.'))
    budget = settings.get('tradeBudget', str(DEFAULT_LIVE_TRADE_BUDGET if live else PAPER_TRADE_BUDGET))
    execution = [
        row('Entry budget', f'{dollars(budget)} before fees. Whole contracts = entry budget divided by ask, rounded down. The budget must cover at least one contract.'),
        row('Frequency', 'One recorded entry per market in this bot’s paper ledger.' if not live else 'One order attempt per market, shared across the live bots. Rejected, unfilled, or uncertain attempts are not automatically retried.'),
        row('Poll interval', f'Normally {amount(poll_seconds if poll_seconds is not None else POLL_SECONDS)} seconds between loops, plus data-fetch time.'),
        row('Execution', 'Simulates buying the requested whole contracts at the ask. Paper costs exclude exchange fees and do not verify available fill depth.' if not live else 'Submits immediate-or-cancel orders. A request may fill fully, partly, or not at all; settled net P/L uses confirmed fills and fees.'),
    ]
    if live:
        cap = settings.get('dailyLimit', MAX_LIVE_TRADES_PER_DAY)
        execution.extend([
            row('Daily order cap', 'Disabled: no daily attempt cap.' if cap == 0 else f'{cap} attempts per UTC day, shared by both live bots. Includes rejected and unfilled attempts.'),
            row('Live process', 'One live bot process at a time; paper bots can run alongside it.'),
            row('Daily loss stop', 'Disabled.'),
        ])
    return [
        section('Entry rules', row('Bought side', sides), *entries),
        section('Entry checks', *filters),
        section('Sizing and execution', *execution),
        section('Exits', row('Settlement', 'Holds until the market resolves. No early take-profit, trailing exit, or stop-loss sale.'),
                row('Stop button', 'Stops new evaluation and entries. It does not close existing positions or cancel exchange orders.' if live else 'Stops evaluating new entries. Logged paper positions remain pending until settlement is checked.')),
    ]


def scalp_settings():
    import scalp_bot as runner
    return {name: getattr(runner, name) for name in (
        'POLL_SECONDS', 'CONTRACTS', 'ALLOWED_SIDES', 'COOLDOWN_SECONDS',
        'MIN_SECONDS_REMAINING', 'TRAILING_ACTIVATION', 'TRAILING_GIVEBACK', 'STOP_LOSS',
    )}


def configured_rule_descriptions(rules, *, override=None, scalp=False):
    descriptions = []
    if not rules:
        return [row('Entry rules', 'No extra filters; entries use the candle strategy.' if scalp else 'No entry rules. The bot will wait without taking new trades.')]
    for index, rule in enumerate(rules, 1):
        band = override or parse_entry_price_range(rule['priceRange'])
        side = 'YES or NO' if rule['side'] == 'BOTH' else rule['side']
        detail = (f"{'Enabled' if rule['enabled'] else 'Disabled'}. At most {rule['maxMinutesLeft']} minutes left; BTC at least {dollars(rule['minBtcDistance'])} from target. "
                  f"Buy {side} at {amount(band['min'] * 100)}¢–{amount(band['max'] * 100)}¢ inclusive. "
                  + ('Requires 3 strictly matching BTC moves.' if rule['requireDirection'] else 'Uses the normal momentum checks.'))
        descriptions.append(row(f"{index}. {rule['name']}", detail))
    descriptions.append(row('Rule order', 'The first enabled rule matching time, distance, and side is selected. If its price or direction checks fail, lower-priority rules are not tried.'))
    return descriptions


def scalp_rules(config=None, *, entry_price_range=None, entry_rules=None):
    from scalp_strategy import MIN_ENTRY_PRICE, MAX_ENTRY_PRICE, MAX_SPREAD
    config = config or scalp_settings()
    custom = parse_entry_price_range(entry_price_range)
    low, high = (custom['min'], custom['max']) if custom else (MIN_ENTRY_PRICE, MAX_ENTRY_PRICE)
    sections = [
        section('Entry rules',
                row('Allowed sides', ', '.join(config['ALLOWED_SIDES']) or 'No sides enabled.'),
                row('Candles', 'Builds 5-second and 15-second candles from locally polled Coinbase BTC-USD ticks. Needs at least 3 closed 5-second candles and 1 closed 15-second candle; the currently forming candles are excluded.'),
                row('Momentum', 'At least 2 of the latest 3 closed 5-second candles must point in the buy direction, including the latest candle. The latest closed 15-second candle must agree. Rising candles select YES; falling candles select NO.'),
                row('Candle body', 'The latest 5-second candle body must be at least as large as the preceding body. A flat latest candle cannot trigger entry.'),
                row('Ask band', f'{amount(low * 100)}¢–{amount(high * 100)}¢ inclusive for the purchased side.'),
                row('Spread', f'At most {amount(MAX_SPREAD * 100)}¢.'),
                row('Entry cutoff', f'When the countdown is available, no new entry below {amount(config["MIN_SECONDS_REMAINING"])} seconds remaining.')),
        section('Sizing and frequency',
                row('Contracts', f'{config["CONTRACTS"]} whole contracts per entry.'),
                row('Open positions', 'One in-memory paper position at a time. Multiple entries per market are allowed after exits and cooldown.'),
                row('Cooldown', f'{amount(config["COOLDOWN_SECONDS"])} seconds after an exit.'),
                row('Poll interval', f'Normally {amount(config["POLL_SECONDS"])} seconds between loops, plus data-fetch time.'),
                row('Execution', 'Paper only: buys at the side’s ask and marks exits at its bid. No actual exchange orders or fees.')),
        section('Exit rules, in priority order',
                row('Market rollover', 'When the selected market changes and quotes are available, the current code closes the paper position using the newly fetched side bid. That is a simulated mark, not a verified fill in the previous market.'),
                row('Stop loss', f'Exit when total position P/L is at or below −{dollars(config["STOP_LOSS"])}. This is checked per poll; a price gap can produce a larger simulated loss.'),
                row('Trailing giveback', f'After total open profit reaches {dollars(config["TRAILING_ACTIVATION"])}, exit when P/L gives back at least {dollars(config["TRAILING_GIVEBACK"])} from its peak. Thresholds apply to the entire position, not each contract.'),
                row('Shrinking candles', 'Exit if the latest 3 closed 5-second candle bodies strictly decrease in size, including when the position is losing.')),
        section('Process behavior',
                row('Data errors', 'Recognized feed/API connection errors clear candle history before retrying. An open in-memory position is retained during those retries. Other exceptions terminate the process.'),
                row('Stop or restart', 'Stopping ends the process without automatically recording a sale. Open positions are not restored from the CSV on restart.')),
    ]
    if entry_rules is not None:
        configured = validate_entry_rules(entry_rules, 'scalp_paper')
        sections[0]['items'].extend(configured_rule_descriptions(configured, override=custom, scalp=True))
        if configured:
            for item in sections[0]['items']:
                if item['label'] == 'Ask band':
                    item['detail'] = 'Uses the price band of the selected entry filter, or the explicit global price override.'
    return sections


def reported_rules(bot_id, runtime, *, settings):
    current = build_bot_rules(bot_id, settings=settings)
    saved = (runtime.get('settings') or {}).get('ruleSnapshot') if runtime.get('processAlive') else None
    if isinstance(saved, dict) and saved.get('schemaVersion') == 1 and saved.get('botId') == bot_id and isinstance(saved.get('sections'), list):
        return {**saved, 'source': 'running', 'matchesCurrent': saved.get('fingerprint') == current['fingerprint']}
    return {**current, 'source': 'current', 'runningWithoutSnapshot': bool(runtime.get('processAlive'))}
