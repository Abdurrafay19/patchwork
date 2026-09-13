def test_first_page_is_valid():
    assert is_valid_page(0, 10, 5) is True


def test_last_valid_page():
    assert is_valid_page(1, 10, 5) is True


def test_one_past_last_page_is_invalid():
    assert is_valid_page(2, 10, 5) is False


def test_negative_page_is_invalid():
    assert is_valid_page(-1, 10, 5) is False
