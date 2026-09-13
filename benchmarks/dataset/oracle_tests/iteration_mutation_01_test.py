def test_consecutive_evens_removed():
    nums = [1, 2, 4, 6, 7]
    assert remove_evens(nums) == [1, 7]


def test_all_evens():
    nums = [2, 4, 6]
    assert remove_evens(nums) == []