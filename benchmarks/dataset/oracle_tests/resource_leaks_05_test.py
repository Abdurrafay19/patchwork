from unittest.mock import mock_open, patch


def test_file_handle_is_closed():
    m = mock_open(read_data='{"a": 1}')
    with patch("builtins.open", m):
        result = read_json_file("dummy.json")
    assert result == {"a": 1}
    assert m.return_value.__exit__.called
