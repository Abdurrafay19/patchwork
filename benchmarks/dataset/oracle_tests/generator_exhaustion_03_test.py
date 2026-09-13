def test_preserves_first_positive_item():
    gen = (x for x in [5, -2, 10])
    assert get_positive_items(gen) == [5, 10]


def test_no_positives():
    gen = (x for x in [-1, -2])
    assert get_positive_items(gen) == []