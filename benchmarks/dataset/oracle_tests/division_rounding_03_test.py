def test_two_minutes_exactly():
    assert convert_seconds_to_minutes(120) == 2


def test_partial_minute_is_discarded():
    assert convert_seconds_to_minutes(125) == 2


def test_less_than_a_minute_is_zero():
    assert convert_seconds_to_minutes(59) == 0
