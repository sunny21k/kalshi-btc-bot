"""Per-bot dashboard preferences. Never starts or controls a process."""

import json
import hashlib
import os
import tempfile
from pathlib import Path

from entry_prices import serialize_entry_price_range
from entry_rules import BOT_IDS, default_entry_rules, validate_entry_rules


def read_bot_settings(root):
    path = Path(root) / 'data' / 'bot_settings.json'
    try:
        settings = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Could not read data/bot_settings.json; fix the settings file before starting a bot') from exc
    if not isinstance(settings, dict):
        raise ValueError('data/bot_settings.json must contain per-bot settings')
    return settings


def saved_entry_price_range(root, bot_id):
    config = read_bot_settings(root).get(bot_id, {})
    if not isinstance(config, dict):
        raise ValueError(f'Invalid saved settings for {bot_id}')
    return serialize_entry_price_range(config.get('entryPriceRange'))


def save_entry_price_range(root, bot_id, value):
    save_bot_config(root, bot_id, {'entryPriceRange': serialize_entry_price_range(value)})


def save_bot_config(root, bot_id, updates):
    settings = read_bot_settings(root)
    config = settings.get(bot_id, {})
    if not isinstance(config, dict):
        raise ValueError(f'Invalid saved settings for {bot_id}')
    settings[bot_id] = {**config, **updates}
    path = Path(root) / 'data' / 'bot_settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.bot-settings-', delete=False) as file:
            temporary = file.name
            json.dump(settings, file, indent=2)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def default_bot_preferences(bot_id):
    if bot_id not in BOT_IDS:
        raise ValueError('Unknown bot')
    result = {'entryRules': default_entry_rules(bot_id), 'entryPriceRange': None}
    if bot_id != 'scalp_paper':
        from paper_execution import PAPER_TRADE_BUDGET
        from live_execution import DEFAULT_LIVE_TRADE_BUDGET, MAX_LIVE_TRADES_PER_DAY
        live = bot_id in ('btc15_live', 'btc15_dual_live')
        result['tradeBudget'] = f'{DEFAULT_LIVE_TRADE_BUDGET if live else PAPER_TRADE_BUDGET:.2f}'
        if live:
            result['dailyLiveOrderLimit'] = MAX_LIVE_TRADES_PER_DAY
    return result


def validate_bot_preferences(bot_id, value):
    from trade_sizing import parse_trade_budget
    from live_execution import parse_daily_live_trade_limit
    defaults = default_bot_preferences(bot_id)
    if not isinstance(value, dict) or set(value) != set(defaults):
        raise ValueError('Settings have missing or unsupported fields')
    rules = validate_entry_rules(value['entryRules'], bot_id)
    if rules is None:
        raise ValueError('Entry rules must be a list; use Restore defaults to reset them')
    result = {'entryRules': rules, 'entryPriceRange': serialize_entry_price_range(value['entryPriceRange'])}
    if 'tradeBudget' in defaults:
        result['tradeBudget'] = f"{parse_trade_budget(value['tradeBudget']):.2f}"
    if 'dailyLiveOrderLimit' in defaults:
        result['dailyLiveOrderLimit'] = parse_daily_live_trade_limit(value['dailyLiveOrderLimit'])
    return result


def configured_bot_preferences(root, bot_id):
    config = read_bot_settings(root).get(bot_id, {})
    if not isinstance(config, dict):
        raise ValueError(f'Invalid saved settings for {bot_id}')
    defaults = default_bot_preferences(bot_id)
    values = {key: config.get(key, value) for key, value in defaults.items()}
    values['entryRules'] = validate_entry_rules(values['entryRules'], bot_id)
    if values['entryRules'] is None:
        raise ValueError('Saved entry rules must be a list')
    # Carry the earlier global price setting into the new per-rule editor.
    band = serialize_entry_price_range(values['entryPriceRange'])
    if band and bot_id != 'scalp_paper':
        values['entryRules'] = [{**rule, 'priceRange': band} for rule in values['entryRules']]
        values['entryPriceRange'] = None
    return validate_bot_preferences(bot_id, values)


def saved_entry_rules(root, bot_id):
    config = read_bot_settings(root).get(bot_id, {})
    if not isinstance(config, dict):
        raise ValueError(f'Invalid saved settings for {bot_id}')
    return validate_entry_rules(config.get('entryRules'), bot_id)


def preferences_fingerprint(preferences):
    return hashlib.sha256(json.dumps(preferences, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
