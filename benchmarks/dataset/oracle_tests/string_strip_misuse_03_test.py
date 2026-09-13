def test_domain_ending_with_characters_in_suffix():
    assert strip_domain_suffix("telecom.com") == "telecom"


def test_standard_domain():
    assert strip_domain_suffix("example.com") == "example"
