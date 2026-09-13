def test_equal_tuples_different_identity():
    c1 = (100.5, 200.5)
    c2 = (100.0 + 0.5, 200.0 + 0.5)
    assert are_same_coordinates(c1, c2) is True