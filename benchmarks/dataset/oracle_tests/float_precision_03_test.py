def test_accepts_rounding_error():
    assert has_reached_target(sum([0.1, 0.1, 0.1]), 0.3) is True


def test_rejects_genuinely_wrong_total():
    assert has_reached_target(1.0, 2.0) is False
