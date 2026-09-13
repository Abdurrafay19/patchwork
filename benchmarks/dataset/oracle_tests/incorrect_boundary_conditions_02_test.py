import pytest


def test_exact_minimum_length_is_valid():
    assert validate_password("abcdefgh") is True


def test_longer_password_is_valid():
    assert validate_password("abcdefghij") is True


def test_too_short_password_raises():
    with pytest.raises(ValueError):
        validate_password("abc")
