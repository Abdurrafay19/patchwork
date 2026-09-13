import pytest


def test_valid_positive_age_returned():
    assert validate_age(30) == 30


def test_missing_age_raises():
    with pytest.raises(ValueError):
        validate_age(None)


def test_zero_age_is_valid():
    assert validate_age(0) == 0
