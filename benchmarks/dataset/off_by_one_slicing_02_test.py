def test_last_two_items():
    assert get_last_n_items([1, 2, 3, 4, 5], 2) == [4, 5]


def test_last_one_item():
    assert get_last_n_items([1, 2, 3], 1) == [3]
