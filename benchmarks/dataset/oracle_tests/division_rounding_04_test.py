def test_no_remainder():
    assert get_remainder_items(9, 3) == 0


def test_with_remainder():
    assert get_remainder_items(10, 3) == 1
