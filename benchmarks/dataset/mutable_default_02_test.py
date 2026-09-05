def test_first_call_starts_empty():
    result = add_tag("urgent")
    assert result == ["urgent"]


def test_second_call_does_not_see_first_calls_tag():
    add_tag("urgent")
    result = add_tag("archived")
    assert result == ["archived"]


def test_duplicate_tag_not_added_twice():
    tags = ["urgent"]
    result = add_tag("urgent", tags)
    assert result == ["urgent"]
