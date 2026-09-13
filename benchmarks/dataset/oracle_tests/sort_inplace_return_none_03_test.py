def test_sorts_by_age():
    users = [{"age": 30}, {"age": 20}, {"age": 25}]
    assert sort_users_by_age(users) == [{"age": 20}, {"age": 25}, {"age": 30}]
