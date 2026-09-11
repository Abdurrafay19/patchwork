def test_first_call_starts_empty():
    result = append_item("a")
    assert result == ["a"]


def test_second_call_does_not_see_first_calls_item():
    append_item("a")
    result = append_item("b")
    assert result == ["b"]


def test_explicit_target_list_still_works():
    target = []
    result = append_item("x", target)
    assert result == ["x"]
