def test_replaces_spaces_with_hyphens():
    assert make_slug("hello world") == "hello-world"


def test_lowercases_letters():
    assert make_slug("Hello World") == "hello-world"
