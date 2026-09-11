from unittest.mock import mock_open, patch


def test_file_handle_is_closed():
    m = mock_open(read_data="hello")
    with patch("builtins.open", m):
        result = read_file_contents("dummy.txt")
    assert result == "hello"
    assert m.return_value.__exit__.called
