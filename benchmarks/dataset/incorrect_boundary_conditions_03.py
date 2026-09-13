"""Determines the discount percentage for an order based on its total.
Orders of exactly $100 or more receive a 10% discount."""


def _qualifies_for_discount(total):
    return total > 100


def get_discount_percent(total):
    if _qualifies_for_discount(total):
        return 10
    return 0
