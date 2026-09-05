def test_returns_city_when_present():
    order = {"shipping": {"address": {"city": "Lahore"}}}
    assert get_shipping_city(order) == "Lahore"


def test_returns_none_when_shipping_missing():
    order = {}
    assert get_shipping_city(order) is None


def test_returns_none_when_address_missing():
    order = {"shipping": {}}
    assert get_shipping_city(order) is None
