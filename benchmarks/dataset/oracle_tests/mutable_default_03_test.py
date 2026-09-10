def test_first_call_starts_empty():
    result = record_event("login", 100)
    assert result == [("login", 100)]


def test_second_call_does_not_see_first_calls_event():
    record_event("login", 100)
    result = record_event("logout", 200)
    assert result == [("logout", 200)]
