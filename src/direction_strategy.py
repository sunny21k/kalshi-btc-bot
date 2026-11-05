"""Paper experiment: keep the entry rules and require a clean strong-rule trend."""

from decimal import Decimal

from strategy import make_late_momentum_decision


def consecutive_direction_matches(side, recent_prices):
    prices = [Decimal(str(price)) for price in (recent_prices or [])][-4:]
    if len(prices) < 4 or not all(price.is_finite() and price > 0 for price in prices):
        return False
    moves = [right - left for left, right in zip(prices, prices[1:])]
    return all(move > 0 for move in moves) if side == "YES" else (
        all(move < 0 for move in moves) if side == "NO" else False
    )


def make_direction_paper_decision(**kwargs):
    kwargs["enable_early_up"] = False
    if kwargs.get('entry_rules') is not None:
        return make_late_momentum_decision(**kwargs)
    result = make_late_momentum_decision(**kwargs)
    if result.get("strategy_name") != "strong_5m_50":
        return result
    result = {**result, "strategy_name": "strong_5m_50_direction"}
    if result["decision"] not in ("BUY YES", "BUY NO"):
        return result
    if not consecutive_direction_matches(result["side"], kwargs.get("recent_prices")):
        return {**result, "decision": "WAIT", "reason": f"need 3 consecutive BTC moves {'up' if result['side'] == 'YES' else 'down'} for {result['side']}"}
    return {**result, "reason": "strong 5-minute $50 rule with 3 matching BTC moves"}
