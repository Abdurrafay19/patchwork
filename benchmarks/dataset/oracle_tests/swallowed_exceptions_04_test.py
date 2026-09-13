import pytest


def test_divides_all_values():
    assert divide_all([10, 20, 30], 2) == [5.0, 10.0, 15.0]


def test_zero_divisor_raises_zero_division_error():
    with pytest.raises(ZeroDivisionError):
        divide_all([10, 20], 0)
