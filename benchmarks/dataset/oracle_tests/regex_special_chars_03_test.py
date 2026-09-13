def test_bracketed_tag():
    assert starts_with_tag("v_release", "[v1]") is False


def test_matching_tag():
    assert starts_with_tag("[v1] Initial commit", "[v1]") is True
