def test_multiplier_sequence():
    multipliers = make_multipliers(3)
    results = [m(2) for m in multipliers]
    assert results == [0, 2, 4]


def test_multiplier_single():
    multipliers = make_multipliers(1)
    assert multipliers[0](5) == 0