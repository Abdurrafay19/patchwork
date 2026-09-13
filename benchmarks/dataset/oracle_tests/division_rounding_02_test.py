def test_exact_multiple():
    assert calculate_full_batches(9, 3) == 3


def test_with_remainder_floors_down():
    assert calculate_full_batches(10, 3) == 3
