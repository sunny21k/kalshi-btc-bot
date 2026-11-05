"""Read-only descriptions built from the strategy constants used by each runner."""

import hashlib
import json
from decimal import Decimal


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
        sections = scalp_rules(settings.get('scalp'))
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
    cents = lambda price: f'{amount(price * 100)}¢'
    band = lambda low, high: f'{cents(low)}–{cents(high)} inclusive'
    sides = 'NO only, when BTC is below the target.' if no_only else 'YES above the BTC target; NO below it.'
    entries = []
    if early_up:
        entries.append(row('Early YES entry', f'At most {amount(rules.MAX_EARLY_UP_ENTRY_SECONDS / 60)} minutes left and BTC at least {dollars(rules.MIN_EARLY_UP_PRICE_DIFFERENCE)} above target. YES ask: {band(rules.MIN_LATE_ENTRY_PRICE, rules.MAX_STRONG_RULE_ENTRY_PRICE)}.'))
    entries.extend([
        row('5-minute rule', f'At most {amount(rules.MAX_STRONG_ENTRY_SECONDS / 60)} minutes left and BTC at least {dollars(rules.MIN_STRONG_BTC_PRICE_DIFFERENCE)} from target. Ask for the purchased side: {band(strong_min, rules.MAX_STRONG_RULE_ENTRY_PRICE)}.'),
        row('4-minute rule', f'At most {amount(rules.MAX_LATE_ENTRY_SECONDS / 60)} minutes left and BTC at least {dollars(rules.MIN_BTC_PRICE_DIFFERENCE)} from target. Ask for the purchased side: {band(rules.MIN_LATE_ENTRY_PRICE, rules.MAX_LATE_RULE_ENTRY_PRICE)}.'),
        row('Rule priority', ('Early YES first, then the 5-minute rule, then the 4-minute rule.' if early_up else 'The 5-minute rule takes priority over the 4-minute rule.') + ' If the selected rule fails a price or momentum check, it does not fall back to a lower-priority rule.'),
    ])
    filters = [
        row('Market data', 'Needs an active BTC 15-minute market, its target price, and usable Kalshi order-book quotes. BTC movement uses Coinbase BTC-USD ticks, sampled separately from contract prices.'),
        row('Close cutoff', f'No entry with {amount(rules.MIN_SECONDS_TO_CLOSE)} seconds or less remaining.'),
        row('Spread', f'At most {cents(rules.MAX_ENTRY_SPREAD)} between the quoted bid and ask.'),
        row('Threshold confirmations', f'Requires {rules.MIN_CONFIRMATION_POLLS} recorded polls with BTC at least {dollars(rules.MIN_BTC_PRICE_DIFFERENCE)} from target on the selected side. The counter resets inside that distance. The strong rule checks its larger distance separately on the current poll.'),
        row('BTC momentum', 'Needs at least 3 samples. Across the latest 3–4 BTC prices, the net movement must match the bought side, and the newest move must agree or be flat. YES uses rising BTC; NO uses falling BTC.'),
        row('Reversal filter', f'With 4 samples, rejects YES if BTC has fallen {dollars(rules.MAX_REVERSAL_DOLLARS)} or more from the window high; rejects NO if BTC has risen that much from the window low.'),
        row('Ask chase', f'Rejects an entry if its ask has increased by more than {cents(rules.MAX_ASK_CHASE_MOVE)} since the previous evaluated ask for that market and side.'),
    ]
    if direction:
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


def scalp_rules(config=None):
    from scalp_strategy import MIN_ENTRY_PRICE, MAX_ENTRY_PRICE, MAX_SPREAD
    config = config or scalp_settings()
    return [
        section('Entry rules',
                row('Allowed sides', ', '.join(config['ALLOWED_SIDES']) or 'No sides enabled.'),
                row('Candles', 'Builds 5-second and 15-second candles from locally polled Coinbase BTC-USD ticks. Needs at least 3 closed 5-second candles and 1 closed 15-second candle; the currently forming candles are excluded.'),
                row('Momentum', 'At least 2 of the latest 3 closed 5-second candles must point in the buy direction, including the latest candle. The latest closed 15-second candle must agree. Rising candles select YES; falling candles select NO.'),
                row('Candle body', 'The latest 5-second candle body must be at least as large as the preceding body. A flat latest candle cannot trigger entry.'),
                row('Ask band', f'{amount(MIN_ENTRY_PRICE * 100)}¢–{amount(MAX_ENTRY_PRICE * 100)}¢ inclusive for the purchased side.'),
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


def reported_rules(bot_id, runtime, *, settings):
    current = build_bot_rules(bot_id, settings=settings)
    saved = (runtime.get('settings') or {}).get('ruleSnapshot') if runtime.get('processAlive') else None
    if isinstance(saved, dict) and saved.get('schemaVersion') == 1 and saved.get('botId') == bot_id and isinstance(saved.get('sections'), list):
        return {**saved, 'source': 'running', 'matchesCurrent': saved.get('fingerprint') == current['fingerprint']}
    return {**current, 'source': 'current', 'runningWithoutSnapshot': bool(runtime.get('processAlive'))}
