import pytest


def test_returns_first_key():
    assert get_first_key({"a": 1, "b": 2}) == "a"


def test_returns_none_for_empty_dict():
    assert get_first_key({}) is None


def test_none_input_raises_attribute_error():
    with pytest.raises(AttributeError):
        get_first_key(None)
