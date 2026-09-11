def test_returns_email_when_present():
    user = {"profile": {"email": "a@example.com"}}
    assert get_user_email(user) == "a@example.com"


def test_returns_none_when_profile_missing():
    user = {}
    assert get_user_email(user) is None


def test_returns_none_when_email_missing():
    user = {"profile": {}}
    assert get_user_email(user) is None
