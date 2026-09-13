def test_strips_prefix_without_corrupting_host():
    assert strip_url_prefix("https://site.com") == "site.com"


def test_strips_exact_protocol_only():
    assert strip_url_prefix("https://history.org") == "history.org"
