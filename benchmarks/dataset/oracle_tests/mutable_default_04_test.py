def test_first_call_starts_empty():
    result = increment_count("a")
    assert result == {"a": 1}


def test_second_call_does_not_see_first_calls_counts():
    increment_count("a")
    result = increment_count("b")
    assert result == {"b": 1}


def test_same_key_increments_within_explicit_dict():
    counts = {}
    increment_count("a", counts)
    result = increment_count("a", counts)
    assert result == {"a": 2}
