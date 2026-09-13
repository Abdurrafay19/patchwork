def test_admin_only_access():
    assert is_accessible(True, False) is True


def test_neither_access():
    assert is_accessible(False, False) is False
