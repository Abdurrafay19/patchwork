def test_positive_balance_has_balance():
    assert get_balance_status(150.0) == "has balance"


def test_none_balance_is_unknown():
    assert get_balance_status(None) == "unknown"


def test_zero_balance_is_not_unknown():
    assert get_balance_status(0.0) == "has balance"
