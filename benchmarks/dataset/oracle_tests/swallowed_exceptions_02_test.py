import pytest


def test_returns_first_positive():
    assert get_first_positive([-1, -2, 3, 4]) == 3


def test_returns_none_when_no_positive():
    assert get_first_positive([-1, -2]) is None


def test_non_iterable_raises_type_error():
    with pytest.raises(TypeError):
        get_first_positive(None)
