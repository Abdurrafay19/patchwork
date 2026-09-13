def test_inside_range():
    assert is_in_valid_range(5, 1, 10) is True


def test_outside_range():
    assert is_in_valid_range(0, 1, 10) is False
    assert is_in_valid_range(15, 1, 10) is False
