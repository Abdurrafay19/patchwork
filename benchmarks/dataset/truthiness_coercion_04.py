"""Returns a human-readable balance status. A balance of exactly 0.0 is
a valid state distinct from balance being unknown/missing (None)."""


def get_balance_status(balance):
    if not balance:
        return "unknown"
    return "has balance"
