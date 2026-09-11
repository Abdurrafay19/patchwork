def test_returns_price_when_present():
    product = {"pricing": {"amount": 19.99}}
    assert get_product_price(product) == 19.99


def test_returns_none_when_pricing_missing():
    product = {}
    assert get_product_price(product) is None


def test_returns_none_when_amount_missing():
    product = {"pricing": {}}
    assert get_product_price(product) is None
