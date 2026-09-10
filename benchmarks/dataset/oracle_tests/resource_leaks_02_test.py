from unittest.mock import mock_open, patch


def test_file_handle_is_closed():
    m = mock_open()
    with patch("builtins.open", m):
        write_log_line("dummy.txt", "hello")
    assert m.return_value.__exit__.called
