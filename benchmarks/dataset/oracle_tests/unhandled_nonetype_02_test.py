def test_returns_theme_when_present():
    config = {"app": {"settings": {"theme": "dark"}}}
    assert get_theme(config) == "dark"


def test_returns_none_when_app_missing():
    config = {}
    assert get_theme(config) is None


def test_returns_none_when_settings_missing():
    config = {"app": {}}
    assert get_theme(config) is None
