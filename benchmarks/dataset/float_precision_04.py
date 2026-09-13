def discount_applied_correctly(price, discount_rate, expected_price):
    return price * (1 - discount_rate) == expected_price
