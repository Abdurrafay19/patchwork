import pytest


def test_matching_header_and_row():
    assert map_headers_to_row(["id", "name"], [1, "Alice"]) == {
        "id": 1,
        "name": "Alice",
    }


def test_missing_row_values_raises_value_error():
    with pytest.raises(ValueError):
        map_headers_to_row(["id", "name", "age"], [1, "Alice"])
