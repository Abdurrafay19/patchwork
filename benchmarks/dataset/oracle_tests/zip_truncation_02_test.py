import pytest


def test_valid_dot_product():
    assert calculate_dot_product([1, 2, 3], [4, 5, 6]) == 32


def test_unequal_dimensions_raises_value_error():
    with pytest.raises(ValueError):
        calculate_dot_product([1, 2], [1, 2, 3])
