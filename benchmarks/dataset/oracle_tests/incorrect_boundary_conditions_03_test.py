def test_exactly_100_qualifies():
    assert get_discount_percent(100) == 10


def test_above_100_qualifies():
    assert get_discount_percent(150) == 10


def test_below_100_does_not_qualify():
    assert get_discount_percent(99) == 0
