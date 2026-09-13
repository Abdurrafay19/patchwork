import pytest


def test_returns_value_for_present_key():
    assert get_config_value({"a": 1}, "a") == 1


def test_returns_none_for_missing_key():
    assert get_config_value({"a": 1}, "b") is None


def test_non_dict_config_raises_type_error():
    with pytest.raises(TypeError):
        get_config_value(None, "a")
