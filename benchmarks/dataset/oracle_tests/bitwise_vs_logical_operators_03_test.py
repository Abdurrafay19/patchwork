def test_even_and_positive():
    assert is_even_and_positive(4) is True


def test_negative_even():
    assert is_even_and_positive(-2) is False
