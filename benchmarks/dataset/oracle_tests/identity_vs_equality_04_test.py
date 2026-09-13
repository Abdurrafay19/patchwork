def test_redirect_codes():
    code_301 = int("301")
    code_302 = int("302")
    assert is_redirect_code(code_301) is True
    assert is_redirect_code(code_302) is True
    assert is_redirect_code(200) is False