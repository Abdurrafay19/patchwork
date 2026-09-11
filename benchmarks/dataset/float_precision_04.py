"""Checks whether applying discount_rate to price yields expected_price,
treating floating-point rounding error as an acceptable match."""


def discount_applied_correctly(price, discount_rate, expected_price):
    return price * (1 - discount_rate) == expected_price
