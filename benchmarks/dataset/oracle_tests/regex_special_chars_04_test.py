def test_domain_with_dots():
    assert is_matching_domain("user@axb.com", "a.b.com") is False


def test_exact_domain_match():
    assert is_matching_domain("user@a.b.com", "a.b.com") is True
