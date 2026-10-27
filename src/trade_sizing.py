from decimal import Decimal, InvalidOperation


def parse_trade_budget(value):
    try:
        budget = Decimal(str(value))
        if not budget.is_finite() or budget <= 0:
            raise ValueError("Trade budget must be a positive dollar amount")
        cents = budget.quantize(Decimal("0.01"))
        if budget != cents:
            raise ValueError("Trade budget must have at most two decimal places")
        return cents
    except InvalidOperation as exc:
        raise ValueError("Invalid dollar budget") from exc


def contracts_for_budget(entry_price, budget):
    try:
        entry_price = Decimal(str(entry_price))
    except InvalidOperation as exc:
        raise ValueError("Invalid entry price") from exc
    if not entry_price.is_finite() or not Decimal("0") < entry_price <= Decimal("1"):
        raise ValueError("Entry price must be greater than $0 and at most $1")
    budget = parse_trade_budget(budget)
    if budget < entry_price:
        raise ValueError("Trade budget must cover at least one contract")
    return int(budget // entry_price)
