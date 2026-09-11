def test_inclusive_range_sum():
    assert sum_range([1, 2, 3, 4, 5], 1, 3) == 9  # indices 1,2,3 -> 2+3+4


def test_single_index_range():
    assert sum_range([10, 20, 30], 1, 1) == 20
