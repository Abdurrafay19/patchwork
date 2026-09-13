def test_removes_consecutive_banned():
    words = ["keep", "bad", "bad", "stay"]
    assert filter_banned_words(words, {"bad"}) == ["keep", "stay"]


def test_no_banned():
    words = ["apple", "orange"]
    assert filter_banned_words(words, {"banana"}) == ["apple", "orange"]    