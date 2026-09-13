def test_escaped_dot_extension():
    assert matches_file_extension("fileatxt", ".txt") is False


def test_valid_extension_match():
    assert matches_file_extension("document.txt", ".txt") is True
