def test_trims_whitespace():
    assert normalize_email("  user@example.com  ") == "user@example.com"


def test_lowercases_letters():
    assert normalize_email("User@Example.com") == "user@example.com"
