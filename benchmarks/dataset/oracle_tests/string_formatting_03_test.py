def test_short_text_unchanged():
    assert truncate_with_ellipsis("hi", 10) == "hi"


def test_long_text_truncated_with_ellipsis():
    assert truncate_with_ellipsis("hello world", 5) == "hello..."
