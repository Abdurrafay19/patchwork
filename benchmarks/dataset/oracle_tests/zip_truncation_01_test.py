import pytest


def test_equal_length_coords():
    assert pair_coordinates([1, 2], [10, 20]) == [(1, 10), (2, 20)]


def test_mismatched_coords_raises_value_error():
    with pytest.raises(ValueError):
        pair_coordinates([1, 2, 3], [10, 20])
