def test_positive_id_is_authenticated():
    assert is_authenticated({"id": 42}) is True


def test_missing_id_is_not_authenticated():
    assert is_authenticated({}) is False


def test_zero_id_is_authenticated():
    assert is_authenticated({"id": 0}) is True
