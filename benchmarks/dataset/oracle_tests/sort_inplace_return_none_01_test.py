def test_returns_descending_scores():
    assert get_sorted_scores([10, 50, 20]) == [50, 20, 10]


def test_does_not_return_none():
    result = get_sorted_scores([1, 2])
    assert result is not None
