def test_valid_percentage():
    assert is_valid_percentage(50.0) is True


def test_invalid_percentage():
    assert is_valid_percentage(-1.0) is False
    assert is_valid_percentage(105.0) is False
