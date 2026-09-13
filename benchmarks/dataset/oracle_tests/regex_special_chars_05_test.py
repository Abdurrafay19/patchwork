def test_keyword_with_parentheses():
    text = "Important note and (note)"
    assert count_keyword_occurrences(text, "(note)") == 1
