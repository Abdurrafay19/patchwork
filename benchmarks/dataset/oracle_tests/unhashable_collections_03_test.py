def test_distinct_users():
    users = [{"name": "A", "role": "admin"}, {"name": "A", "role": "admin"}]
    assert find_distinct_user_profiles(users) == [{"name": "A", "role": "admin"}]
