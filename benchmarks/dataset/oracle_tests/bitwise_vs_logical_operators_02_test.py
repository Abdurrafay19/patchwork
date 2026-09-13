def test_positive_dimensions():
    assert is_valid_dimension(10, 20) is True


def test_negative_width():
    assert is_valid_dimension(-5, 20) is False
