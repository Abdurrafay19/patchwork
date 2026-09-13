def test_alphabetical_ordering():
    assert get_alphabetical_tags(["zebra", "apple", "mango"]) == [
        "apple",
        "mango",
        "zebra",
    ]


def test_does_not_return_none():
    assert get_alphabetical_tags(["b", "a"]) == ["a", "b"]
