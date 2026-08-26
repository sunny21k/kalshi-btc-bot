from kalshi_api import get_market


def get_market_result(ticker):
    """
    Get the final result for a Kalshi market.

    Returns:
        "YES"  -> market resolved YES
        "NO"   -> market resolved NO
        None   -> market is not finalized yet
    """

    response = get_market(ticker)
    market = response.get("market", {})

    status = market.get("status")
    result = market.get("result")

    if status != "finalized":
        return None

    if result == "yes":
        return "YES"

    if result == "no":
        return "NO"

    return None


def prediction_was_correct(signal, result):
    """
    Compare our signal with the actual Kalshi result.

    UP + YES  = correct
    DOWN + NO = correct

    NEUTRAL is ignored because we don't trade it.
    """

    if result is None:
        return None

    if signal == "UP":
        return result == "YES"

    if signal == "DOWN":
        return result == "NO"

    return None
