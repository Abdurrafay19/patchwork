def test_accepts_rounding_error():
    # 0.1 + 0.2 != 0.3 exactly in float -- must not use bare ==
    assert is_total_correct(0.1, 0.2, 0.3) is True


def test_rejects_genuinely_wrong_total():
    assert is_total_correct(1.0, 1.0, 3.0) is False
