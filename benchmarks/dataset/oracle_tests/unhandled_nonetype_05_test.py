def test_returns_name_when_present():
    employee = {"manager": {"name": "Sam"}}
    assert get_manager_name(employee) == "Sam"


def test_returns_none_when_manager_missing():
    employee = {}
    assert get_manager_name(employee) is None


def test_returns_none_when_name_missing():
    employee = {"manager": {}}
    assert get_manager_name(employee) is None
