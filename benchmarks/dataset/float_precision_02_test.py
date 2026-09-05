def test_accepts_rounding_error():
    assert average_equals([0.1, 0.2, 0.3], 0.2) is True


def test_rejects_genuinely_wrong_average():
    assert average_equals([1.0, 2.0, 3.0], 5.0) is False
