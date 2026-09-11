def test_accepts_rounding_error():
    assert is_zero(1.0 - 0.9 - 0.1) is True


def test_rejects_genuinely_nonzero_value():
    assert is_zero(1.0) is False
