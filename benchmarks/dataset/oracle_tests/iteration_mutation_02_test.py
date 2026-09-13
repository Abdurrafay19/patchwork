def test_strips_none_keys():
    d = {"a": 1, "b": None, "c": 3, "d": None}
    assert strip_none_keys(d) == {"a": 1, "c": 3}


def test_no_none_keys():
    d = {"x": 10, "y": 20}
    assert strip_none_keys(d) == {"x": 10, "y": 20}