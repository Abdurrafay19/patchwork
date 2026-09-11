def test_first_page():
    assert get_page_items([1, 2, 3, 4, 5, 6], 0, 3) == [1, 2, 3]


def test_second_page():
    assert get_page_items([1, 2, 3, 4, 5, 6], 1, 3) == [4, 5, 6]
