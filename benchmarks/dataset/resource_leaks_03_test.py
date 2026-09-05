from unittest.mock import mock_open, patch


def test_file_handle_is_closed():
    m = mock_open(read_data="a\nb\nc\n")
    with patch("builtins.open", m):
        result = count_lines("dummy.txt")
    assert result == 3
    assert m.return_value.__exit__.called
