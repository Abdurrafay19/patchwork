def test_returns_configured_page_size():
    assert get_page_size({"page_size": 25}) == 25


def test_returns_default_when_not_set():
    assert get_page_size({}) == 10


def test_zero_page_size_is_preserved():
    assert get_page_size({"page_size": 0}) == 0
