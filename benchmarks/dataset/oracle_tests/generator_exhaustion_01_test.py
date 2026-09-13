def test_with_generator():
    gen = (x * 2 for x in [1, 5, 3])
    assert calculate_range(gen) == 8


def test_with_list():
    assert calculate_range([10, 20, 30]) == 20