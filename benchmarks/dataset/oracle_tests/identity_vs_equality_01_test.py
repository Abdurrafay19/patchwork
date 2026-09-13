def test_constructed_string_equality():
    constructed = "".join(["COMP", "LETED"])
    assert is_successful_status(constructed) is True


def test_different_status():
    assert is_successful_status("PENDING") is False