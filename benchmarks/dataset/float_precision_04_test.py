def test_accepts_rounding_error():
    assert discount_applied_correctly(4.35, 0.1, 3.915) is True


def test_rejects_genuinely_wrong_price():
    assert discount_applied_correctly(10.0, 0.1, 5.0) is False
