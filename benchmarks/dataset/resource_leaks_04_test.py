from unittest.mock import mock_open, patch


def test_file_handle_is_closed():
    m = mock_open(read_data="a \n b \n c\n")
    with patch("builtins.open", m):
        result = read_stripped_lines("dummy.txt")
    assert result == ["a", "b", "c"]
    assert m.return_value.__exit__.called
