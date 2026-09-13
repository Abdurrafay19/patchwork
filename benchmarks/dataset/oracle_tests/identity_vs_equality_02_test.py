def test_dynamically_computed_port():
    computed_port = int("8080")
    assert is_standard_port(computed_port) is True


def test_wrong_port():
    assert is_standard_port(80) is False