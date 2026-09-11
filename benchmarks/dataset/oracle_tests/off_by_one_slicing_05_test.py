def test_first_five_chars():
    assert first_n_chars("hello world", 5) == "hello"


def test_first_one_char():
    assert first_n_chars("abc", 1) == "a"
